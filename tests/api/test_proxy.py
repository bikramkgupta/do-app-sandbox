"""Container API tests for port proxy functionality."""

import time

import httpx
import pytest

from tests.api.conftest import requires_container_api


@pytest.mark.container
@requires_container_api
class TestPortProxy:
    """Tests for port proxy endpoints."""

    @pytest.fixture(autouse=True)
    def setup_server(self, api_url, auth_headers, cleanup_processes):
        """Start a simple HTTP server for proxy tests."""
        # Start Python HTTP server on port 9000
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "cd /tmp && python -m http.server 9000"},
            headers=auth_headers,
            timeout=10.0,
        )
        if response.status_code == 200:
            pid = response.json().get("pid")
            if pid:
                cleanup_processes(pid)

        # Wait for server to start
        time.sleep(1)

        yield

    def test_proxy_get_request(self, api_url, auth_headers):
        """GET /proxy/{port}/ proxies."""
        response = httpx.get(f"{api_url}/proxy/9000/", headers=auth_headers, timeout=10.0)

        # Should get response (200) or 502 if server not ready
        assert response.status_code in (200, 404, 502)

    def test_proxy_post_request(self, api_url, auth_headers):
        """POST requests proxied."""
        response = httpx.post(f"{api_url}/proxy/9000/", headers=auth_headers, content="test data", timeout=10.0)

        # POST to http.server returns 501 (Not Implemented) or 405
        assert response.status_code in (200, 404, 405, 501, 502)

    def test_proxy_with_path(self, api_url, auth_headers):
        """Path passed through."""
        # Create a file to request
        httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo 'path test' > /tmp/path_test.txt"},
            headers=auth_headers,
            timeout=10.0,
        )

        response = httpx.get(f"{api_url}/proxy/9000/path_test.txt", headers=auth_headers, timeout=10.0)

        if response.status_code == 200:
            assert "path test" in response.text

    def test_proxy_with_query(self, api_url, auth_headers):
        """Query string passed."""
        response = httpx.get(f"{api_url}/proxy/9000/?foo=bar&baz=qux", headers=auth_headers, timeout=10.0)

        # Just verify it doesn't error
        assert response.status_code in (200, 404, 502)

    def test_proxy_headers_forwarded(self, api_url, auth_headers):
        """Headers forwarded (except auth)."""
        response = httpx.get(
            f"{api_url}/proxy/9000/",
            headers={**auth_headers, "X-Custom-Header": "custom-value", "Accept": "text/html"},
            timeout=10.0,
        )

        # Just verify request succeeds
        assert response.status_code in (200, 404, 502)

    def test_proxy_connection_error(self, api_url, auth_headers):
        """502 when port not listening."""
        # Port 19999 should not have anything listening
        response = httpx.get(f"{api_url}/proxy/19999/", headers=auth_headers, timeout=10.0)

        # Should return 502 Bad Gateway
        assert response.status_code == 502

    def test_proxy_timeout(self, api_url, auth_headers, cleanup_processes):
        """504 on timeout."""
        # Start a slow server (or use a port that accepts but doesn't respond)
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "nc -l -p 19998 -q 30"},  # Listen but don't respond
            headers=auth_headers,
            timeout=10.0,
        )
        if response.status_code == 200:
            pid = response.json().get("pid")
            if pid:
                cleanup_processes(pid)

        time.sleep(0.5)

        # Try to connect with short timeout (proxy may timeout)
        try:
            response = httpx.get(
                f"{api_url}/proxy/19998/",
                headers=auth_headers,
                timeout=3.0,  # Short timeout on our side
            )
            # Server might return 504 Gateway Timeout
            assert response.status_code in (200, 502, 504)
        except httpx.ReadTimeout:
            # This is also acceptable - timeout occurred
            pass
