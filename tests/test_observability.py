import pytest
from fastapi.testclient import TestClient
from main import app
from auth import security_scheme

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "timestamp_utc" in data
    assert "uptime_seconds" in data
    assert "dependencies" in data
    assert "firestore" in data["dependencies"]


def test_admin_metrics_without_token_unauthorized():
    response = client.get("/admin/metrics")
    assert response.status_code == 401
    assert "detail" in response.json()


def test_admin_logs_without_token_unauthorized():
    response = client.get("/admin/logs")
    assert response.status_code == 401


def test_observability_middleware_headers():
    response = client.get("/")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert "X-Response-Time-Ms" in response.headers

