from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    cached: bool
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
