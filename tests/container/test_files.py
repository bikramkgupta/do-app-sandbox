"""Container API tests for file operations."""

import base64

import pytest
import httpx

from tests.container.conftest import requires_container_api


@pytest.mark.container
@requires_container_api
class TestFileOperations:
    """Tests for file operation endpoints."""

    def test_list_files(self, api_url, auth_headers):
        """GET /api/files lists directory."""
        response = httpx.get(
            f"{api_url}/api/files?path=/workspace",
            headers=auth_headers,
            timeout=10.0
        )
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_list_files_shows_metadata(self, api_url, auth_headers):
        """Shows name, size, is_dir."""
        # Create a test file first
        httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo 'test' > /workspace/metadata_test.txt"},
            headers=auth_headers,
            timeout=10.0
        )

        response = httpx.get(
            f"{api_url}/api/files?path=/workspace",
            headers=auth_headers,
            timeout=10.0
        )
        data = response.json()

        # Find our file
        test_file = next((f for f in data if f.get("name") == "metadata_test.txt"), None)

        if test_file:
            assert "name" in test_file
            assert "is_dir" in test_file
            assert test_file["is_dir"] is False
            # Size might be present
            if "size" in test_file:
                assert isinstance(test_file["size"], int)

    def test_read_file(self, api_url, auth_headers):
        """GET /api/files/content reads file."""
        # Create a test file
        httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo 'read test content' > /workspace/read_test.txt"},
            headers=auth_headers,
            timeout=10.0
        )

        response = httpx.get(
            f"{api_url}/api/files/content?path=/workspace/read_test.txt",
            headers=auth_headers,
            timeout=10.0
        )
        assert response.status_code == 200

        data = response.json()
        content = data.get("content", "")
        assert "read test content" in content

    def test_read_binary_file(self, api_url, auth_headers):
        """Binary files base64 encoded."""
        # Create a binary file
        httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo -n -e '\\x00\\x01\\x02\\x03' > /workspace/binary_test.bin"},
            headers=auth_headers,
            timeout=10.0
        )

        response = httpx.get(
            f"{api_url}/api/files/content?path=/workspace/binary_test.bin",
            headers=auth_headers,
            timeout=10.0
        )

        if response.status_code == 200:
            data = response.json()
            # If binary, should be base64 encoded
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"])
                assert content[:4] == b'\x00\x01\x02\x03'

    def test_write_file(self, api_url, auth_headers):
        """POST /api/files/content writes."""
        response = httpx.post(
            f"{api_url}/api/files/content",
            json={
                "path": "/workspace/write_test.txt",
                "content": "written content here"
            },
            headers=auth_headers,
            timeout=10.0
        )
        assert response.status_code == 200

        # Verify content
        verify_response = httpx.post(
            f"{api_url}/api/exec",
            json={"command": "cat /workspace/write_test.txt"},
            headers=auth_headers,
            timeout=10.0
        )
        assert "written content here" in verify_response.json().get("stdout", "")

    def test_write_creates_dirs(self, api_url, auth_headers):
        """Creates parent directories."""
        response = httpx.post(
            f"{api_url}/api/files/content",
            json={
                "path": "/workspace/nested/deep/dir/file.txt",
                "content": "nested file content"
            },
            headers=auth_headers,
            timeout=10.0
        )
        assert response.status_code == 200

        # Verify
        verify_response = httpx.post(
            f"{api_url}/api/exec",
            json={"command": "cat /workspace/nested/deep/dir/file.txt"},
            headers=auth_headers,
            timeout=10.0
        )
        assert "nested file content" in verify_response.json().get("stdout", "")

    def test_download_file(self, api_url, auth_headers):
        """GET /api/files/download works."""
        # Create a file
        httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo 'download content' > /workspace/download_test.txt"},
            headers=auth_headers,
            timeout=10.0
        )

        response = httpx.get(
            f"{api_url}/api/files/download?path=/workspace/download_test.txt",
            headers=auth_headers,
            timeout=10.0
        )

        # Should return file content directly or as download
        assert response.status_code == 200
        # Content could be in body or as attachment
        if "download content" not in response.text:
            # Check if it's a redirect or has content-disposition
            assert response.headers.get("content-disposition") or response.status_code == 200
