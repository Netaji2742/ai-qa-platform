from unittest.mock import patch

from app.llm_client import LLMResult


def _fake_llm_result(**overrides):
    defaults = dict(
        answer="42",
        prompt_tokens=5,
        completion_tokens=1,
        latency_ms=12.3,
        used_fallback=False,
    )
    defaults.update(overrides)
    return LLMResult(**defaults)


def test_chat_requires_auth(client):
    resp = client.post("/chat", json={"question": "What is the meaning of life?"})
    assert resp.status_code == 401


@patch("app.routers.chat.call_llm")
def test_chat_success(mock_call_llm, client, auth_headers):
    mock_call_llm.return_value = _fake_llm_result()
    resp = client.post(
        "/chat", json={"question": "What is the meaning of life?"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "42"
    assert body["cached"] is False
    assert body["prompt_tokens"] == 5
    mock_call_llm.assert_called_once()


@patch("app.routers.chat.call_llm")
def test_chat_cache_hit_on_second_call(mock_call_llm, client, auth_headers):
    mock_call_llm.return_value = _fake_llm_result()
    question = "Explain Docker layer caching"

    first = client.post("/chat", json={"question": question}, headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["cached"] is False

    second = client.post("/chat", json={"question": question}, headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["cached"] is True
    # LLM should only have been called once — second answer came from cache
    mock_call_llm.assert_called_once()


@patch("app.routers.chat.call_llm")
def test_chat_llm_fallback_is_surfaced(mock_call_llm, client, auth_headers):
    mock_call_llm.return_value = _fake_llm_result(
        answer="The AI service is temporarily unavailable. Please try again shortly.",
        prompt_tokens=0,
        completion_tokens=0,
        used_fallback=True,
    )
    resp = client.post(
        "/chat", json={"question": "unique-uncached-question"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert "temporarily unavailable" in resp.json()["answer"]


def test_chat_rejects_empty_question(client, auth_headers):
    resp = client.post("/chat", json={"question": ""}, headers=auth_headers)
    assert resp.status_code == 422
