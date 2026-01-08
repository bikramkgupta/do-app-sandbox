"""Container API tests for health check endpoint."""

import pytest
import httpx

from tests.container.conftest import requires_container_api


@pytest.mark.container
@requires_container_api
class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_endpoint(self, api_url):
        """GET /health returns 200."""
        response = httpx.get(f"{api_url}/health", timeout=10.0)
        assert response.status_code == 200

    def test_health_response_format(self, api_url):
        """Response has status and mode fields."""
        response = httpx.get(f"{api_url}/health", timeout=10.0)
        data = response.json()

        assert "status" in data
        assert data["status"] == "healthy"
        # Mode might be present
        if "mode" in data:
            assert data["mode"] in ("service", "worker")

    def test_health_no_auth_required(self, api_url):
        """/health works without token."""
        # No auth headers
        response = httpx.get(f"{api_url}/health", timeout=10.0)
        assert response.status_code == 200
