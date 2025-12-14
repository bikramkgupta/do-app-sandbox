"""Image registry management for custom sandbox images."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .types import ImageInfo, ValidationResult


class ImageRegistry:
    """Manages the local registry of custom sandbox images."""

    BUILT_IN_IMAGES = {"python", "node"}

    def __init__(self, config_dir: Optional[str] = None):
        """Initialize the image registry.

        Args:
            config_dir: Directory to store registry data.
                       Defaults to ~/.config/app-platform-sandbox/
        """
        if config_dir is None:
            config_dir = os.path.expanduser("~/.config/app-platform-sandbox")
        self.config_dir = Path(config_dir)
        self.registry_file = self.config_dir / "images.json"
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Create config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> Dict:
        """Load registry data from file."""
        if not self.registry_file.exists():
            return {"images": {}}
        with open(self.registry_file, "r") as f:
            return json.load(f)

    def _save_registry(self, data: Dict) -> None:
        """Save registry data to file."""
        with open(self.registry_file, "w") as f:
            json.dump(data, f, indent=2)

    def add_image(
        self,
        name: str,
        dockerfile_path: str,
        registry: str,
        validation_log: Optional[str] = None,
    ) -> ImageInfo:
        """Register a new custom image for validation.

        Args:
            name: Unique name for the image
            dockerfile_path: Path to the Dockerfile
            registry: DOCR registry URL
            validation_log: Path to write validation logs

        Returns:
            ImageInfo with status "validating"

        Raises:
            ValueError: If name conflicts with built-in or existing image
        """
        if name in self.BUILT_IN_IMAGES:
            raise ValueError(f"Cannot use reserved name: {name}")

        registry_data = self._load_registry()
        if name in registry_data["images"]:
            raise ValueError(f"Image '{name}' already exists. Remove it first.")

        # Generate image URL
        image_url = f"registry.digitalocean.com/{registry}/sandbox-{name}:latest"

        # Set default validation log path
        if validation_log is None:
            validation_log = f"/tmp/sandbox-validate-{name}.log"

        now = datetime.utcnow().isoformat() + "Z"

        image_data = {
            "dockerfile_path": os.path.abspath(dockerfile_path),
            "registry": registry,
            "image_url": image_url,
            "status": "validating",
            "created_at": now,
            "validated_at": None,
            "validation_pid": None,
            "validation_log": validation_log,
            "validation_results": None,
        }

        registry_data["images"][name] = image_data
        self._save_registry(registry_data)

        return self._dict_to_image_info(name, image_data)

    def get_image(self, name: str) -> Optional[ImageInfo]:
        """Get information about a registered image.

        Args:
            name: Image name

        Returns:
            ImageInfo if found, None otherwise
        """
        if name in self.BUILT_IN_IMAGES:
            return ImageInfo(
                name=name,
                dockerfile_path="<built-in>",
                registry="<built-in>",
                image_url="<built-in>",
                status="validated",
                created_at="<built-in>",
                validated_at="<built-in>",
            )

        registry_data = self._load_registry()
        if name not in registry_data["images"]:
            return None

        return self._dict_to_image_info(name, registry_data["images"][name])

    def list_images(self) -> List[ImageInfo]:
        """List all registered images including built-ins.

        Returns:
            List of ImageInfo for all images
        """
        images = []

        # Add built-in images
        for name in sorted(self.BUILT_IN_IMAGES):
            images.append(
                ImageInfo(
                    name=name,
                    dockerfile_path="<built-in>",
                    registry="<built-in>",
                    image_url="<built-in>",
                    status="validated",
                    created_at="<built-in>",
                    validated_at="<built-in>",
                )
            )

        # Add custom images
        registry_data = self._load_registry()
        for name, data in sorted(registry_data["images"].items()):
            images.append(self._dict_to_image_info(name, data))

        return images

    def remove_image(self, name: str) -> bool:
        """Remove a custom image from the registry.

        Args:
            name: Image name to remove

        Returns:
            True if removed, False if not found

        Raises:
            ValueError: If trying to remove built-in image
        """
        if name in self.BUILT_IN_IMAGES:
            raise ValueError(f"Cannot remove built-in image: {name}")

        registry_data = self._load_registry()
        if name not in registry_data["images"]:
            return False

        del registry_data["images"][name]
        self._save_registry(registry_data)
        return True

    def update_status(
        self,
        name: str,
        status: str,
        validation_pid: Optional[int] = None,
        validation_results: Optional[ValidationResult] = None,
    ) -> Optional[ImageInfo]:
        """Update the status of a registered image.

        Args:
            name: Image name
            status: New status ("validating", "validated", "failed")
            validation_pid: PID of validation process
            validation_results: Validation results if complete

        Returns:
            Updated ImageInfo, or None if not found
        """
        registry_data = self._load_registry()
        if name not in registry_data["images"]:
            return None

        registry_data["images"][name]["status"] = status

        if validation_pid is not None:
            registry_data["images"][name]["validation_pid"] = validation_pid

        if validation_results is not None:
            registry_data["images"][name]["validation_results"] = {
                "dockerfile_parsed": validation_results.dockerfile_parsed,
                "has_expose_8080": validation_results.has_expose_8080,
                "has_entrypoint": validation_results.has_entrypoint,
                "image_built": validation_results.image_built,
                "container_started": validation_results.container_started,
                "health_check_passed": validation_results.health_check_passed,
                "error": validation_results.error,
            }

        if status == "validated":
            registry_data["images"][name]["validated_at"] = (
                datetime.utcnow().isoformat() + "Z"
            )
            registry_data["images"][name]["validation_pid"] = None

        self._save_registry(registry_data)
        return self._dict_to_image_info(name, registry_data["images"][name])

    def is_image_ready(self, name: str) -> bool:
        """Check if an image is validated and ready for use.

        Args:
            name: Image name

        Returns:
            True if image is ready (built-in or validated)
        """
        if name in self.BUILT_IN_IMAGES:
            return True

        image = self.get_image(name)
        return image is not None and image.status == "validated"

    def get_image_url(self, name: str, registry: Optional[str] = None) -> Optional[str]:
        """Get the Docker image URL for a registered image.

        Args:
            name: Image name
            registry: Override registry for built-in images

        Returns:
            Image URL or None if not found/ready
        """
        if name in self.BUILT_IN_IMAGES:
            if registry is None:
                return None
            return f"registry.digitalocean.com/{registry}/sandbox-{name}:latest"

        image = self.get_image(name)
        if image is None or image.status != "validated":
            return None

        return image.image_url

    def _dict_to_image_info(self, name: str, data: Dict) -> ImageInfo:
        """Convert registry dict to ImageInfo dataclass."""
        validation_results = None
        if data.get("validation_results"):
            vr = data["validation_results"]
            validation_results = ValidationResult(
                dockerfile_parsed=vr.get("dockerfile_parsed", False),
                has_expose_8080=vr.get("has_expose_8080", False),
                has_entrypoint=vr.get("has_entrypoint", False),
                image_built=vr.get("image_built", False),
                container_started=vr.get("container_started", False),
                health_check_passed=vr.get("health_check_passed", False),
                error=vr.get("error"),
            )

        return ImageInfo(
            name=name,
            dockerfile_path=data["dockerfile_path"],
            registry=data["registry"],
            image_url=data["image_url"],
            status=data["status"],
            created_at=data["created_at"],
            validated_at=data.get("validated_at"),
            validation_pid=data.get("validation_pid"),
            validation_log=data.get("validation_log"),
            validation_results=validation_results,
        )
