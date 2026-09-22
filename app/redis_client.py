import hashlib
import time

import redis

from app.config import get_settings

settings = get_settings()

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


def cache_key_for_question(question: str) -> str:
    digest = hashlib.sha256(question.strip().lower().encode()).hexdigest()
    return f"chat:cache:{digest}"


def get_cached_answer(question: str) -> str | None:
    return redis_client.get(cache_key_for_question(question))


def set_cached_answer(question: str, answer: str) -> None:
    redis_client.setex(cache_key_for_question(question), settings.CACHE_TTL_SECONDS, answer)


def check_rate_limit(username: str) -> bool:
    """Simple fixed-window rate limiter keyed by user + current minute.
    Returns True if the request is allowed, False if the limit is exceeded.
    In a multi-instance deployment this correctly enforces a global limit
    because Redis is shared across all FastAPI replicas."""
    window = int(time.time() // 60)
    key = f"ratelimit:{username}:{window}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 60)
    return count <= settings.RATE_LIMIT_PER_MINUTE


def ping() -> bool:
    try:
        return redis_client.ping()
    except Exception:
        return False
