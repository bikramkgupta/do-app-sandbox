"""DigitalOcean Spaces integration for large file transfers."""

import os
import uuid
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

from .exceptions import SpacesNotConfiguredError
from .types import SpacesConfig

# Environment variable names
ENV_SPACES_ACCESS_KEY = "SPACES_ACCESS_KEY"
ENV_SPACES_SECRET_KEY = "SPACES_SECRET_KEY"
ENV_SPACES_BUCKET = "SPACES_BUCKET"
ENV_SPACES_REGION = "SPACES_REGION"
ENV_SPACES_ENDPOINT = "SPACES_ENDPOINT"

# Default large file threshold (5 MB)
DEFAULT_LARGE_FILE_THRESHOLD = 5 * 1024 * 1024
ENV_LARGE_FILE_THRESHOLD = "SANDBOX_LARGE_FILE_THRESHOLD"

# Default presigned URL lifetime (15 minutes)
DEFAULT_PRESIGNED_EXPIRY = 15 * 60


class SpacesClient:
    """Client for DigitalOcean Spaces operations."""

    def __init__(self, config: SpacesConfig):
        """Initialize Spaces client.

        Args:
            config: SpacesConfig with bucket, region, and optional credentials

        Raises:
            SpacesNotConfiguredError: If credentials are missing
        """
        # Normalize region casing to avoid signing/endpoint mismatches
        self.config = config
        self.bucket = config.bucket
        self.region = (config.region or "").lower()
        self.endpoint = config.endpoint or os.environ.get(ENV_SPACES_ENDPOINT)

        # Get credentials from config or environment
        self.access_key = config.access_key or os.environ.get(ENV_SPACES_ACCESS_KEY)
        self.secret_key = config.secret_key or os.environ.get(ENV_SPACES_SECRET_KEY)

        if not self.access_key or not self.secret_key:
            raise SpacesNotConfiguredError(
                f"Spaces credentials required. Set {ENV_SPACES_ACCESS_KEY} and "
                f"{ENV_SPACES_SECRET_KEY} environment variables or pass in SpacesConfig."
            )

        self._client = None
        self.endpoint_url, self.addressing_style = self._resolve_endpoint()

    def _resolve_endpoint(self) -> Tuple[str, str]:
        """Resolve the endpoint URL and addressing style.

        If a bucket-scoped endpoint is provided (e.g. https://bucket.region.digitaloceanspaces.com),
        strip the bucket to avoid double-prefixing in requests and presigned URLs.
        """
        endpoint_env = (self.endpoint or "").strip()
        if endpoint_env:
            endpoint_env = endpoint_env.rstrip("/")
            parsed = urlparse(endpoint_env if "://" in endpoint_env else f"https://{endpoint_env}")

            if parsed.netloc.startswith(f"{self.bucket}."):
                # Drop the bucket prefix to avoid bucket-bucket.host in requests
                netloc = parsed.netloc[len(self.bucket) + 1 :]
                endpoint_url = f"{parsed.scheme}://{netloc}"
            else:
                endpoint_url = f"{parsed.scheme}://{parsed.netloc}"
                if parsed.path:
                    endpoint_url = endpoint_url + parsed.path

            addressing_style = "virtual"
        else:
            endpoint_url = f"https://{self.region}.digitaloceanspaces.com"
            addressing_style = "virtual"

        return endpoint_url, addressing_style

    @property
    def client(self):
        """Lazy initialization of boto3 client."""
        if self._client is None:
            try:
                import boto3
                import botocore.config
            except ImportError:
                raise SpacesNotConfiguredError(
                    "boto3 is required for Spaces operations. Install with: pip install boto3"
                )

            session = boto3.session.Session()
            self._client = session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                config=botocore.config.Config(s3={"addressing_style": self.addressing_style}),
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
        return self._client

    def generate_key(self, sandbox_id: str, filename: str, direction: str = "upload") -> str:
        """Generate a unique Spaces object key.

        Args:
            sandbox_id: Sandbox identifier
            filename: Original filename
            direction: "upload" or "download"

        Returns:
            Unique object key
        """
        unique_id = str(uuid.uuid4())[:8]
        return f"sandbox-{sandbox_id}/{direction}s/{unique_id}/{filename}"

    def upload_file(
        self,
        local_path: str,
        key: str,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """Upload a file to Spaces.

        Args:
            local_path: Path to local file
            key: Spaces object key
            progress_callback: Optional callback(bytes_transferred)

        Returns:
            Object key
        """
        file_size = os.path.getsize(local_path)

        callback = None
        if progress_callback:
            transferred = [0]

            def callback(bytes_amount):
                transferred[0] += bytes_amount
                progress_callback(transferred[0])

        self.client.upload_file(
            local_path,
            self.bucket,
            key,
            Callback=callback,
        )

        return key

    def download_file(
        self,
        key: str,
        local_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """Download a file from Spaces.

        Args:
            key: Spaces object key
            local_path: Path to save file
            progress_callback: Optional callback(bytes_transferred)

        Returns:
            Local path
        """
        callback = None
        if progress_callback:
            transferred = [0]

            def callback(bytes_amount):
                transferred[0] += bytes_amount
                progress_callback(transferred[0])

        self.client.download_file(
            self.bucket,
            key,
            local_path,
            Callback=callback,
        )

        return local_path

    def generate_presigned_download_url(self, key: str, expires_in: int = DEFAULT_PRESIGNED_EXPIRY) -> str:
        """Generate a presigned URL for downloading.

        Args:
            key: Object key
            expires_in: URL expiration in seconds (default 15 minutes)

        Returns:
            Presigned URL
        """
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def generate_presigned_upload_url(self, key: str, expires_in: int = DEFAULT_PRESIGNED_EXPIRY) -> str:
        """Generate a presigned URL for uploading.

        Args:
            key: Object key
            expires_in: URL expiration in seconds (default 15 minutes)

        Returns:
            Presigned URL
        """
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete_object(self, key: str) -> None:
        """Delete an object from Spaces.

        Args:
            key: Object key to delete
        """
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def object_exists(self, key: str) -> bool:
        """Check if an object exists in Spaces.

        Args:
            key: Object key

        Returns:
            True if object exists
        """
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def get_object_size(self, key: str) -> Optional[int]:
        """Get the size of an object in Spaces.

        Args:
            key: Object key

        Returns:
            Size in bytes, or None if not found
        """
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
            return response.get("ContentLength")
        except Exception:
            return None


def get_large_file_threshold() -> int:
    """Get the configured large file threshold.

    Returns:
        Threshold in bytes
    """
    threshold_str = os.environ.get(ENV_LARGE_FILE_THRESHOLD)
    if threshold_str:
        try:
            return int(threshold_str)
        except ValueError:
            pass
    return DEFAULT_LARGE_FILE_THRESHOLD


def create_spaces_config_from_env() -> Optional[SpacesConfig]:
    """Create SpacesConfig from environment variables.

    Returns:
        SpacesConfig if bucket and region are set, None otherwise
    """
    bucket = os.environ.get(ENV_SPACES_BUCKET)
    region = os.environ.get(ENV_SPACES_REGION)

    if not bucket or not region:
        return None

    return SpacesConfig(
        bucket=bucket,
        region=region.lower(),
        access_key=os.environ.get(ENV_SPACES_ACCESS_KEY),
        secret_key=os.environ.get(ENV_SPACES_SECRET_KEY),
        endpoint=os.environ.get(ENV_SPACES_ENDPOINT),
    )
