# AI Question-Answering API

A small, production-shaped FastAPI service that authenticates users with JWT,
answers questions using Gemini (Google), caches responses and enforces
rate limits with Redis, persists an audit log to PostgreSQL, and exposes
health and Prometheus metrics endpoints.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the SSO/OIDC extension, RBAC
model, the 500-RPS scaling scenario, and the EC2 → 10,000-user migration plan.

## Stack

- **API:** Python 3.12, FastAPI, Uvicorn
- **LLM:** Gemini (`google-genai` SDK)
- **Auth:** JWT (`python-jose`), bcrypt password hashing (`passlib`)
- **Cache / rate limiting:** Redis
- **Database:** PostgreSQL (SQLAlchemy ORM)
- **Observability:** `/health`, `/metrics` (Prometheus format)
- **Container:** Docker, Docker Compose

## Project layout

```
app/
  main.py          FastAPI app, middleware, router wiring
  config.py        Env-driven settings (no hard-coded secrets)
  security.py      JWT issue/verify, password hashing, RBAC dependency
  database.py      SQLAlchemy models + session (ChatLog audit table)
  redis_client.py  Response cache + distributed rate limiter
  llm_client.py    Gemini Gateway: timeout, retry/backoff, fallback
  metrics.py       Prometheus counters/histograms
  routers/
    auth.py        POST /auth/login
    chat.py        POST /chat
    health.py      GET /health, GET /metrics
tests/             pytest suite (mocks the LLM call, no real API key needed)
Dockerfile         Multi-stage, non-root runtime image
docker-compose.yml app + Redis + PostgreSQL
ARCHITECTURE.md    Written answers: SSO/OIDC, RBAC, scaling, migration
```

## Quick start (Docker Compose)

```bash
git clone <this-repo>
cd ai-qa-platform
cp .env.example .env
# Edit .env: set GEMINI_API_KEY (free at aistudio.google.com/app/apikey), and generate your own JWT_SECRET_KEY
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up --build
```

The API is now at `http://localhost:8000` (interactive docs at `/docs`).

### Try it — via curl

```bash
# 1. Log in (demo credentials from .env.example: demo / changeme123)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"changeme123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2. Ask a question
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"What is a Kubernetes HPA?"}' | python3 -m json.tool

# 3. Health check
curl -s http://localhost:8000/health | python3 -m json.tool

# 4. Metrics (admin role required — the demo user's DEMO_ROLE is admin)
curl -s http://localhost:8000/metrics -H "Authorization: Bearer $TOKEN"
```

### Try it — via the interactive docs UI

No curl needed — `http://localhost:8000/docs` is a full interactive UI:

1. Expand **POST /auth/login** → "Try it out" → body `{"username": "demo", "password": "changeme123"}` → Execute. Copy the `access_token` from the response.
2. Click the green **Authorize** button near the top of the page → paste the token (no `Bearer ` prefix needed) → Authorize → Close.
3. Expand **POST /chat** → "Try it out" → type a question → Execute. Ask as many questions as you like without logging in again, until the token expires (30 min).

(The Authorize dialog takes a plain pasted token — it isn't the OAuth2 username/password form some FastAPI demos use, because `/auth/login` here is a plain JSON endpoint, not the OAuth2 password-grant flow.)

## Running locally without Docker

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # point DATABASE_URL / REDIS_URL at local instances, or run just those two via compose
uvicorn app.main:app --reload
```

## Running the tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Tests use an in-memory SQLite database and `fakeredis`, and mock the Gemini
call directly — no network access or real API key required to run the suite.
`pytest.ini` sets `pythonpath = .` so the bare `pytest` command resolves the
`app` package correctly regardless of how it's invoked.

## Environment variables

See [.env.example](./.env.example) for the full list. Nothing is
hard-coded in source: JWT secret, demo credentials, database URL, Redis URL,
and the Gemini API key are all read from the environment.

## API summary

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | none | Exchange username/password for a JWT |
| POST | `/chat` | Bearer JWT | Ask a question, get an LLM-generated answer |
| GET | `/health` | none | Liveness/readiness: checks DB + Redis connectivity |
| GET | `/metrics` | Bearer JWT (admin role) | Prometheus scrape endpoint |

`/chat` behavior:
- Checks Redis for a cached answer to the same (normalized) question first.
- On a cache miss, calls Gemini with a bounded timeout, retrying transient
  errors (timeout/connection/rate-limit/5xx) with exponential backoff.
- If every retry fails, returns a safe fallback message instead of a 500.
- Records latency, prompt/completion token counts, and cache-hit status to
  both Prometheus metrics and a `chat_logs` row in PostgreSQL.
- Enforces a per-user, Redis-backed rate limit (shared across replicas).

## Design decisions worth calling out

- **Stateless app tier** — no in-memory session/cache — is what makes
  horizontal scaling (multiple replicas behind a load balancer) safe with no
  code changes; see ARCHITECTURE.md §3.
- **LLM Gateway isolation** (`llm_client.py`) keeps all provider-specific
  logic (timeouts, retries, token accounting) in one place, so swapping or
  adding a fallback LLM provider later doesn't touch route code.
- **RBAC via a dependency factory** (`require_role(*roles)`) means adding a
  new protected route or a new role is a one-line change, not a rewrite.
- **Audit log in Postgres, live counters in Prometheus** — metrics answer
  "what's happening right now," the `chat_logs` table answers "what
  happened and to whom," which is what a real billing/abuse-review feature
  would query.
- **`HTTPBearer` instead of `OAuth2PasswordBearer`** for the security scheme —
  `OAuth2PasswordBearer` makes the Swagger "Authorize" dialog submit a
  form-encoded username/password to the login endpoint, which doesn't match
  our plain JSON `/auth/login`. `HTTPBearer` makes Authorize just accept a
  pasted token, matching how the API is actually meant to be used (log in
  separately, then authorize with the token). A small `Bearer401` subclass
  on top corrects `HTTPBearer`'s default `403` for a missing token to the
  more correct `401`.
