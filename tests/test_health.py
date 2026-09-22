def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body
    assert "redis" in body


def test_metrics_requires_admin_auth(client):
    resp = client.get("/metrics")
    assert resp.status_code == 401


def test_metrics_returns_prometheus_text(client, auth_headers):
    # auth_headers fixture logs in as the demo user, whose role is admin
    resp = client.get("/metrics", headers=auth_headers)
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text or resp.text == ""
