from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)

CHAT_LATENCY = Histogram(
    "chat_request_latency_seconds", "End-to-end /chat request latency in seconds"
)

LLM_LATENCY = Histogram(
    "llm_call_latency_seconds", "Latency of the raw LLM call in seconds"
)

LLM_TOKENS = Counter(
    "llm_tokens_total", "Total LLM tokens consumed", ["type"]  # type=prompt|completion
)

CACHE_HITS = Counter("chat_cache_hits_total", "Number of /chat responses served from cache")

LLM_FALLBACKS = Counter(
    "llm_fallback_total", "Number of times the LLM fallback response was returned"
)
