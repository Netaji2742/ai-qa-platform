"""
LLM Gateway — the only module that talks to the Gemini API.

Keeping this isolated behind a single call_llm() function is what would
let a real deployment add provider fallback (e.g. Gemini -> OpenAI) or a
circuit breaker without touching the API routes at all. Every other
module only ever imports LLMResult / call_llm from here — never the
`google.genai` package directly — so switching providers again later is
a one-file change.
"""
import logging
import time
from dataclasses import dataclass

import httpx
from google import genai
from google.genai import errors as genai_errors
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("llm_client")

client = genai.Client(api_key=settings.GEMINI_API_KEY)


def _is_retryable(exc: BaseException) -> bool:
    """Retry on transient failures only: 5xx server errors, 429 rate
    limits, and network-level timeouts/connection errors. A 4xx client
    error (bad request, invalid key) will fail identically on every
    retry, so those are deliberately NOT retried."""
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", None) == 429:
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    return False


@dataclass
class LLMResult:
    answer: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    used_fallback: bool


@retry(
    reraise=True,
    stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    retry=retry_if_exception(_is_retryable),
)
def _call_gemini(question: str):
    return client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=question,
        config={"http_options": {"timeout": int(settings.LLM_TIMEOUT_SECONDS * 1000)},
                "thinking_config": {"thinking_level": "low"},                
        },
    )


def call_llm(question: str) -> LLMResult:
    """Send a question to Gemini. Retries transient errors (5xx, 429,
    timeout, connection) with exponential backoff. If every retry is
    exhausted, or a non-retryable error occurs, falls back to a safe
    canned response rather than raising a 500 straight to the user.
    """
    start = time.perf_counter()
    try:
        response = _call_gemini(question)
        latency_ms = (time.perf_counter() - start) * 1000
        usage = response.usage_metadata
        return LLMResult(
            answer=response.text or "",
            prompt_tokens=usage.prompt_token_count or 0,
            completion_tokens=usage.candidates_token_count or 0,
            latency_ms=latency_ms,
            used_fallback=False,
        )
    except Exception as exc:  # noqa: BLE001 - intentional catch-all for fallback
        latency_ms = (time.perf_counter() - start) * 1000
        logger.error("LLM call failed after retries: %s", exc)
        return LLMResult(
            answer=settings.LLM_FALLBACK_MESSAGE,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            used_fallback=True,
        )
