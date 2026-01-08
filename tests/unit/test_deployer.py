"""Tests for deployer.py - Deployer Service Mode Tests."""

import json
from unittest.mock import MagicMock, patch

import pytest

from do_app_sandbox.types import SandboxMode, ServiceConfig


class TestWorkerSpecGeneration:
    """Tests for worker mode spec generation."""

    def test_worker_spec_uses_worker_template(self):
        """Worker mode generates worker spec (no HTTP port)."""
        from do_app_sandbox.deployer import Deployer

        deployer = Deployer(
            registry="test-registry",
            region="nyc1",
            instance_size="apps-s-1vcpu-1gb"
        )

        spec, token = deployer._generate_app_spec(
            name="test-sandbox",
            image="python",
            component_type="worker",
            mode=SandboxMode.WORKER
        )

        # Worker spec should have workers section, not services
        assert "workers:" in spec
        assert "services:" not in spec
        assert "http_port:" not in spec
        assert token is None  # No token for worker mode

    def test_worker_spec_has_correct_image(self):
        """Worker spec uses worker image repository."""
        from do_app_sandbox.deployer import Deployer, IMAGE_REPOS

        deployer = Deployer(registry="test-registry")

        spec, _ = deployer._generate_app_spec(
            name="test-sandbox",
            image="python",
            mode=SandboxMode.WORKER
        )

        # Should use sandbox-python (worker), not sandbox-python-service
        assert IMAGE_REPOS["python"] in spec
        assert "sandbox-python-service" not in spec


class TestServiceSpecGeneration:
    """Tests for service mode spec generation."""

    def test_service_spec_uses_streaming_template(self):
        """Service mode generates streaming service spec."""
        from do_app_sandbox.deployer import Deployer

        deployer = Deployer(
            registry="test-registry",
            region="sfo3"
        )

        spec, token = deployer._generate_app_spec(
            name="test-sandbox",
            image="python",
            mode=SandboxMode.SERVICE
        )

        # Service spec should have services section
        assert "services:" in spec
        assert "http_port: 8080" in spec
        assert token is not None  # Token generated for service mode

    def test_service_spec_has_correct_image(self):
        """Service spec uses service image repository."""
        from do_app_sandbox.deployer import Deployer, SERVICE_IMAGE_REPOS

        deployer = Deployer(registry="test-registry")

        spec, _ = deployer._generate_app_spec(
            name="test-sandbox",
            image="python",
            mode=SandboxMode.SERVICE
        )

        # Should use sandbox-python-service
        assert SERVICE_IMAGE_REPOS["python"] in spec


class TestServiceTokenGeneration:
    """Tests for service token generation."""

    def test_service_token_generated(self):
        """Service mode generates random token."""
        from do_app_sandbox.deployer import Deployer

        deployer = Deployer(registry="test-registry")

        _, token1 = deployer._generate_app_spec(
            name="test-1",
            image="python",
            mode=SandboxMode.SERVICE
        )

        _, token2 = deployer._generate_app_spec(
            name="test-2",
            image="python",
            mode=SandboxMode.SERVICE
        )

        assert token1 is not None
        assert token2 is not None
        assert token1 != token2  # Random, should be different
        assert len(token1) > 20  # secrets.token_urlsafe(32) is ~43 chars

    def test_custom_token_used(self):
        """Custom token from ServiceConfig is used."""
        from do_app_sandbox.deployer import Deployer

        deployer = Deployer(registry="test-registry")
        config = ServiceConfig(token="my-custom-token-123")

        _, token = deployer._generate_app_spec(
            name="test-sandbox",
            image="python",
            mode=SandboxMode.SERVICE,
            service_config=config
        )

        assert token == "my-custom-token-123"


class TestServiceSpecEnvToken:
    """Tests for SANDBOX_API_TOKEN env var in spec."""

    def test_service_spec_includes_env_token(self):
        """Service spec includes SANDBOX_API_TOKEN env var."""
        from do_app_sandbox.deployer import Deployer

        deployer = Deployer(registry="test-registry")

        spec, token = deployer._generate_app_spec(
            name="test-sandbox",
            image="python",
            mode=SandboxMode.SERVICE
        )

        assert "SANDBOX_API_TOKEN" in spec
        assert token in spec  # Token value should be in spec

    def test_service_spec_token_is_secret(self):
        """SANDBOX_API_TOKEN is marked as SECRET type."""
        from do_app_sandbox.deployer import Deployer

        deployer = Deployer(registry="test-registry")

        spec, _ = deployer._generate_app_spec(
            name="test-sandbox",
            image="python",
            mode=SandboxMode.SERVICE
        )

        # Check env var config
        assert "type: SECRET" in spec
        assert "SANDBOX_API_TOKEN" in spec


class TestServiceSpecHealthCheck:
    """Tests for health check configuration in service spec."""

    def test_service_spec_has_health_check(self):
        """Service spec has health check on /health."""
        from do_app_sandbox.deployer import Deployer

        deployer = Deployer(registry="test-registry")

        spec, _ = deployer._generate_app_spec(
            name="test-sandbox",
            image="python",
            mode=SandboxMode.SERVICE
        )

        assert "health_check:" in spec
        assert "/health" in spec


class TestImageRepoMapping:
    """Tests for image repository mapping."""

    def test_python_worker_repo(self):
        """Python worker uses sandbox-python repo."""
        from do_app_sandbox.deployer import IMAGE_REPOS

        assert IMAGE_REPOS["python"] == "sandbox-python"

    def test_python_service_repo(self):
        """Python service uses sandbox-python-service repo."""
        from do_app_sandbox.deployer import SERVICE_IMAGE_REPOS

        assert SERVICE_IMAGE_REPOS["python"] == "sandbox-python-service"

    def test_node_worker_repo(self):
        """Node worker uses sandbox-node repo."""
        from do_app_sandbox.deployer import IMAGE_REPOS

        assert IMAGE_REPOS["node"] == "sandbox-node"

    def test_node_service_repo(self):
        """Node service uses sandbox-node-service repo."""
        from do_app_sandbox.deployer import SERVICE_IMAGE_REPOS

        assert SERVICE_IMAGE_REPOS["node"] == "sandbox-node-service"


class TestDeployerDefaults:
    """Tests for deployer default values."""

    def test_default_region(self):
        """Default region is atl1."""
        from do_app_sandbox.deployer import DEFAULT_REGION

        assert DEFAULT_REGION == "atl1"

    def test_default_instance_size(self):
        """Default instance size is apps-s-1vcpu-1gb."""
        from do_app_sandbox.deployer import DEFAULT_INSTANCE_SIZE

        assert DEFAULT_INSTANCE_SIZE == "apps-s-1vcpu-1gb"


class TestDeployerInit:
    """Tests for Deployer initialization."""

    def test_deployer_stores_config(self):
        """Deployer stores configuration values."""
        from do_app_sandbox.deployer import Deployer

        deployer = Deployer(
            registry="my-registry",
            registry_type="GHCR",
            region="sfo3",
            instance_size="apps-s-2vcpu-4gb",
            api_token="test-token"
        )

        assert deployer.registry == "my-registry"
        assert deployer.registry_type == "GHCR"
        assert deployer.region == "sfo3"
        assert deployer.instance_size == "apps-s-2vcpu-4gb"
        assert deployer.api_token == "test-token"

    def test_deployer_default_registry_type(self):
        """Deployer defaults to GHCR registry type."""
        from do_app_sandbox.deployer import Deployer

        deployer = Deployer()

        assert deployer.registry_type == "GHCR"


class TestSpecTemplates:
    """Tests for spec templates structure."""

    def test_worker_spec_template_structure(self):
        """Worker spec template has correct structure."""
        from do_app_sandbox.deployer import WORKER_SPEC_TEMPLATE

        assert "name:" in WORKER_SPEC_TEMPLATE
        assert "region:" in WORKER_SPEC_TEMPLATE
        assert "workers:" in WORKER_SPEC_TEMPLATE
        assert "image:" in WORKER_SPEC_TEMPLATE
        assert "instance_count: 1" in WORKER_SPEC_TEMPLATE

    def test_service_spec_template_structure(self):
        """Service spec template has correct structure."""
        from do_app_sandbox.deployer import SERVICE_SPEC_TEMPLATE

        assert "name:" in SERVICE_SPEC_TEMPLATE
        assert "region:" in SERVICE_SPEC_TEMPLATE
        assert "services:" in SERVICE_SPEC_TEMPLATE
        assert "http_port: 8080" in SERVICE_SPEC_TEMPLATE
        assert "health_check:" in SERVICE_SPEC_TEMPLATE

    def test_streaming_service_spec_template_structure(self):
        """Streaming service spec template has envs and ingress."""
        from do_app_sandbox.deployer import STREAMING_SERVICE_SPEC_TEMPLATE

        assert "envs:" in STREAMING_SERVICE_SPEC_TEMPLATE
        assert "SANDBOX_API_TOKEN" in STREAMING_SERVICE_SPEC_TEMPLATE
        assert "SANDBOX_MODE" in STREAMING_SERVICE_SPEC_TEMPLATE
        assert "ingress:" in STREAMING_SERVICE_SPEC_TEMPLATE
        assert "rules:" in STREAMING_SERVICE_SPEC_TEMPLATE


class TestCreateApp:
    """Tests for create_app method."""

    @patch("do_app_sandbox.deployer.Deployer._run_doctl")
    @patch("do_app_sandbox.deployer.Path")
    @patch("do_app_sandbox.deployer.tempfile.NamedTemporaryFile")
    def test_create_app_returns_app_info(self, mock_tempfile, mock_path, mock_run_doctl):
        """create_app returns AppInfo and token."""
        from do_app_sandbox.deployer import Deployer
        from do_app_sandbox.types import AppInfo

        # Setup mocks
        mock_file = MagicMock()
        mock_file.name = "/tmp/spec.yaml"
        mock_tempfile.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tempfile.return_value.__exit__ = MagicMock(return_value=False)

        mock_run_doctl.return_value = (0, json.dumps([{
            "id": "app-123",
            "spec": {"name": "test-sandbox"},
            "active_deployment": {"phase": "PENDING"},
            "live_url": "https://test-sandbox.ondigitalocean.app",
            "region": {"slug": "nyc1"}
        }]), "")

        mock_path.return_value.unlink = MagicMock()

        deployer = Deployer(registry="test-registry")

        app_info, token = deployer.create_app(
            name="test-sandbox",
            image="python",
            mode=SandboxMode.SERVICE
        )

        assert isinstance(app_info, AppInfo)
        assert app_info.app_id == "app-123"
        assert token is not None  # Service mode generates token

    @patch("do_app_sandbox.deployer.Deployer._run_doctl")
    @patch("do_app_sandbox.deployer.Path")
    @patch("do_app_sandbox.deployer.tempfile.NamedTemporaryFile")
    def test_create_app_worker_no_token(self, mock_tempfile, mock_path, mock_run_doctl):
        """create_app in worker mode returns None token."""
        from do_app_sandbox.deployer import Deployer

        mock_file = MagicMock()
        mock_file.name = "/tmp/spec.yaml"
        mock_tempfile.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tempfile.return_value.__exit__ = MagicMock(return_value=False)

        mock_run_doctl.return_value = (0, json.dumps([{
            "id": "app-456",
            "spec": {"name": "worker-sandbox"}
        }]), "")

        mock_path.return_value.unlink = MagicMock()

        deployer = Deployer(registry="test-registry")

        app_info, token = deployer.create_app(
            name="worker-sandbox",
            image="python",
            mode=SandboxMode.WORKER
        )

        assert token is None  # Worker mode has no token


class TestNodeServiceSpec:
    """Tests for Node.js service mode spec."""

    def test_node_service_spec_uses_correct_image(self):
        """Node service spec uses sandbox-node-service image."""
        from do_app_sandbox.deployer import Deployer, SERVICE_IMAGE_REPOS

        deployer = Deployer(registry="test-registry")

        spec, _ = deployer._generate_app_spec(
            name="node-sandbox",
            image="node",
            mode=SandboxMode.SERVICE
        )

        assert SERVICE_IMAGE_REPOS["node"] in spec
        assert "sandbox-node-service" in spec
