from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import verify_database_connection


def test_application_starts_and_health_returns_expected_response(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "service": "FieldOps AI",
        "version": "0.1.0",
        "environment": "test",
    }


def test_liveness_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "alive",
        "service": "FieldOps AI",
    }


def test_readiness_reports_database_available(client: TestClient) -> None:
    app.dependency_overrides[verify_database_connection] = lambda: True

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": {"status": "ok", "detail": None}},
    }


def test_readiness_reports_database_unavailable_safely(
    client: TestClient,
) -> None:
    app.dependency_overrides[verify_database_connection] = lambda: False

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"]["status"] == "unavailable"
    assert "postgres" not in response.text.lower()
    assert "password" not in response.text.lower()
    assert "asyncpg" not in response.text.lower()


def test_swagger_documentation_is_available(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_request_id_header_is_generated(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_request_id_header_is_preserved(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "test-request-id"},
    )

    assert response.headers["X-Request-ID"] == "test-request-id"
