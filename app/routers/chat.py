import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import ChatLog, get_db
from app.llm_client import call_llm
from app.metrics import CACHE_HITS, CHAT_LATENCY, LLM_FALLBACKS, LLM_TOKENS
from app.redis_client import check_rate_limit, get_cached_answer, set_cached_answer
from app.schemas import ChatRequest, ChatResponse
from app.security import get_current_user

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    if not check_rate_limit(user["username"]):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down.",
        )

    start = time.perf_counter()

    cached_answer = get_cached_answer(payload.question)
    if cached_answer is not None:
        latency_ms = (time.perf_counter() - start) * 1000
        CACHE_HITS.inc()
        CHAT_LATENCY.observe(latency_ms / 1000)
        _log(db, user["username"], payload.question, cached_answer, latency_ms, 0, 0, True, "ok")
        return ChatResponse(
            answer=cached_answer,
            cached=True,
            latency_ms=latency_ms,
            prompt_tokens=0,
            completion_tokens=0,
        )

    result = call_llm(payload.question)
    latency_ms = (time.perf_counter() - start) * 1000

    LLM_TOKENS.labels(type="prompt").inc(result.prompt_tokens)
    LLM_TOKENS.labels(type="completion").inc(result.completion_tokens)
    CHAT_LATENCY.observe(latency_ms / 1000)
    if result.used_fallback:
        LLM_FALLBACKS.inc()
    else:
        set_cached_answer(payload.question, result.answer)

    _log(
        db,
        user["username"],
        payload.question,
        result.answer,
        latency_ms,
        result.prompt_tokens,
        result.completion_tokens,
        False,
        "fallback" if result.used_fallback else "ok",
    )

    return ChatResponse(
        answer=result.answer,
        cached=False,
        latency_ms=latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


def _log(db, username, question, answer, latency_ms, prompt_tokens, completion_tokens, cache_hit, status_):
    entry = ChatLog(
        username=username,
        question=question,
        answer=answer,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_hit=int(cache_hit),
        status=status_,
    )
    db.add(entry)
    db.commit()
