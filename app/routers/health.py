from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.redis_client import ping as redis_ping
from app.schemas import HealthResponse
from app.security import require_role

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unreachable"

    redis_status = "ok" if redis_ping() else "unreachable"
    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(status=overall, database=db_status, redis=redis_status)


@router.get("/metrics", dependencies=[Depends(require_role("admin"))])
def metrics() -> Response:
    """Admin-only: Prometheus scrape target. Restricted per the RBAC policy
    in ARCHITECTURE.md (metrics/config are an Admin-only concern)."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
