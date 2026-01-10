"""Container API tests for the sandbox_api FastAPI server.

These tests validate the FastAPI server that runs inside service-mode containers.
Can be run locally with Docker or against a deployed container.

Test modules:
- test_health.py: Health check endpoint tests
- test_exec.py: Command execution tests
- test_exec_stream.py: Streaming execution tests
- test_background.py: Background process management tests
- test_sessions.py: Session management tests
- test_files.py: File operations tests
- test_proxy.py: Port proxy tests

Running locally:
    docker build -t sandbox-api-test -f images/sandbox-python-service/Dockerfile images/
    docker run -p 8080:8080 -e SANDBOX_API_TOKEN=test-token sandbox-api-test
    SANDBOX_API_URL=http://localhost:8080 SANDBOX_API_TOKEN=test-token pytest tests/container/
"""
