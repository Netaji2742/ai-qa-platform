import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault(
    "DEMO_PASSWORD_HASH",
    "$2b$12$lpBzJMqngW5dZJI1SN6RIOIJ5iOPTRptOCNDSa8HUdXZbMDrtmo76",  # "changeme123"
)
os.environ.setdefault("DEMO_ROLE", "admin")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, redis_client
from app.main import app

# --- In-memory SQLite instead of Postgres for fast, isolated tests ---
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
database.Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[database.get_db] = override_get_db

# --- Fake Redis instead of a real server ---
redis_client.redis_client = fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def auth_headers(client):
    resp = client.post("/auth/login", json={"username": "demo", "password": "changeme123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
