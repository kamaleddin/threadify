"""Tests for health check endpoint."""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """Test that health check endpoint returns ok status."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
