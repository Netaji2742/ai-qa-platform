"""
Centralized, environment-driven configuration.

Every value that could differ between dev/staging/prod (or that is a
secret) is read from the environment. Nothing here is hard-coded; see
.env.example for the full list of variables a deployer must set.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "AI Question-Answering API"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- Auth / JWT ---
    JWT_SECRET_KEY: str  # required, no default — must come from env/secrets manager
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Demo user store (replace with a real IdP / users table in production) ---
    DEMO_USERNAME: str = "demo"
    DEMO_PASSWORD_HASH: str  # bcrypt hash, required from env
    DEMO_ROLE: str = "user"

    # --- Database ---
    DATABASE_URL: str = "postgresql://postgres:postgres@postgres:5432/aiqa"

    # --- Redis ---
    REDIS_URL: str = "redis://redis:6379/0"
    CACHE_TTL_SECONDS: int = 300
    RATE_LIMIT_PER_MINUTE: int = 60

    # --- LLM (Google Gemini) ---
    GEMINI_API_KEY: str  # required, no default — get a free one at aistudio.google.com/app/apikey
    GEMINI_MODEL: str = "gemini-2.5-flash"
    LLM_TIMEOUT_SECONDS: float = 15.0
    LLM_MAX_RETRIES: int = 3
    LLM_FALLBACK_MESSAGE: str = (
        "The AI service is temporarily unavailable. Please try again shortly."
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
