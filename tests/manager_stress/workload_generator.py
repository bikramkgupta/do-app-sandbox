"""
Workload generator module for SandboxManager stress tests.

Selects and configures programs to run in sandboxes based on
category, duration, and image type.
"""

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import ImageType, get_programs_path


@dataclass
class ProgramSpec:
    """Specification for a program to run."""
    name: str
    path: Path
    category: str
    image: ImageType
    extension: str

    def get_command(self, duration_seconds: int) -> str:
        """Get the command to run this program."""
        if self.extension == ".py":
            return f"python {self.path.name} --duration {duration_seconds}"
        elif self.extension == ".js":
            return f"node {self.path.name} --duration {duration_seconds}"
        else:
            raise ValueError(f"Unknown extension: {self.extension}")

    def get_upload_path(self) -> str:
        """Get the path to upload the program to in the sandbox."""
        return f"/home/sandbox/app/{self.path.name}"


class WorkloadGenerator:
    """Generates workloads by selecting appropriate programs."""

    # Category mappings for each image type
    PYTHON_CATEGORIES = {
        "compute": ["fibonacci.py", "prime_sieve.py", "matrix_mult.py", "sort_benchmark.py", "hash_stress.py"],
        "io": ["csv_generate.py", "json_transform.py", "file_copy.py", "temp_file_stress.py", "log_simulator.py", "spaces_upload.py"],
        "network": ["http_client.py", "dns_timing.py"],
        "mixed": ["data_pipeline.py", "text_processing.py", "stats_compute.py", "config_generator.py", "batch_processor.py", "report_generator.py"],
        "idle": ["sleep_random.py", "periodic_heartbeat.py", "intermittent_work.py"],
    }

    NODE_CATEGORIES = {
        "compute": ["fibonacci.js", "prime_sieve.js", "crypto_hash.js", "buffer_ops.js", "sorting.js"],
        "io": ["file_operations.js", "json_processing.js", "stream_copy.js", "csv_generator.js", "log_writer.js"],
        "async": ["promise_chain.js", "concurrent_ops.js", "event_loop_test.js", "timer_stress.js", "queue_processor.js"],
        "mixed": ["data_transform.js", "template_render.js", "config_generator.js", "batch_processor.js", "api_simulator.js"],
        "idle": ["sleep_random.js", "heartbeat.js", "intermittent.js"],
    }

    def __init__(self, programs_dir: Optional[Path] = None):
        self.programs_dir = programs_dir or get_programs_path()
        self._program_cache: dict[str, list[ProgramSpec]] = {}
        self._load_programs()

    def _load_programs(self):
        """Load and index all available programs."""
        # Python programs
        python_dir = self.programs_dir / "python"
        if python_dir.exists():
            for category, programs in self.PYTHON_CATEGORIES.items():
                key = f"python_{category}"
                self._program_cache[key] = []
                category_dir = python_dir / category
                if category_dir.exists():
                    for program_name in programs:
                        program_path = category_dir / program_name
                        if program_path.exists():
                            self._program_cache[key].append(ProgramSpec(
                                name=program_name,
                                path=program_path,
                                category=category,
                                image=ImageType.PYTHON,
                                extension=".py",
                            ))

        # Node programs
        node_dir = self.programs_dir / "node"
        if node_dir.exists():
            for category, programs in self.NODE_CATEGORIES.items():
                key = f"node_{category}"
                self._program_cache[key] = []
                category_dir = node_dir / category
                if category_dir.exists():
                    for program_name in programs:
                        program_path = category_dir / program_name
                        if program_path.exists():
                            self._program_cache[key].append(ProgramSpec(
                                name=program_name,
                                path=program_path,
                                category=category,
                                image=ImageType.NODE,
                                extension=".js",
                            ))

    def get_available_categories(self, image: ImageType) -> list[str]:
        """Get available categories for an image type."""
        prefix = image.value
        return [
            key.replace(f"{prefix}_", "")
            for key in self._program_cache.keys()
            if key.startswith(prefix) and self._program_cache[key]
        ]

    def get_programs_in_category(self, image: ImageType, category: str) -> list[ProgramSpec]:
        """Get all programs in a category."""
        key = f"{image.value}_{category}"
        return self._program_cache.get(key, [])

    def select_program(
        self,
        image: ImageType,
        categories: list[str],
        exclude: Optional[list[str]] = None,
    ) -> Optional[ProgramSpec]:
        """
        Select a random program from the given categories.

        Args:
            image: Image type (python or node)
            categories: List of categories to choose from
            exclude: Optional list of program names to exclude
        """
        exclude = exclude or []

        # Collect all eligible programs
        eligible = []
        for category in categories:
            programs = self.get_programs_in_category(image, category)
            for program in programs:
                if program.name not in exclude:
                    eligible.append(program)

        if not eligible:
            return None

        return random.choice(eligible)

    def select_program_for_duration(
        self,
        image: ImageType,
        categories: list[str],
        duration_seconds: int,
    ) -> Optional[ProgramSpec]:
        """
        Select a program suitable for the given duration.

        Some programs are better suited for longer durations (idle, mixed)
        while others work well for shorter runs (compute, io).
        """
        # Adjust category weights based on duration
        weighted_categories = []

        for category in categories:
            if category in ("idle",):
                # Idle programs are good for any duration
                weight = 1.0
            elif category in ("mixed", "async"):
                # Mixed/async programs work well for medium-long durations
                weight = 1.0 if duration_seconds > 120 else 0.5
            elif category in ("compute", "io"):
                # Compute/IO work well for shorter durations
                weight = 1.0 if duration_seconds < 600 else 0.5
            elif category in ("network", "spaces"):
                # Network/spaces have external dependencies, use less frequently
                weight = 0.3
            else:
                weight = 1.0

            weighted_categories.extend([category] * int(weight * 10))

        if not weighted_categories:
            weighted_categories = categories

        selected_category = random.choice(weighted_categories)
        return self.select_program(image, [selected_category])

    def get_all_programs(self, image: Optional[ImageType] = None) -> list[ProgramSpec]:
        """Get all available programs, optionally filtered by image."""
        programs = []
        for key, specs in self._program_cache.items():
            if image is None or key.startswith(image.value):
                programs.extend(specs)
        return programs

    def get_program_count(self) -> dict[str, int]:
        """Get count of programs by category."""
        counts = {}
        for key, specs in self._program_cache.items():
            counts[key] = len(specs)
        return counts

    def validate_programs(self) -> dict[str, list[str]]:
        """
        Validate that all expected programs exist.

        Returns dict of missing programs by category.
        """
        missing = {}

        # Check Python
        python_dir = self.programs_dir / "python"
        for category, programs in self.PYTHON_CATEGORIES.items():
            category_dir = python_dir / category
            for program in programs:
                if not (category_dir / program).exists():
                    key = f"python_{category}"
                    if key not in missing:
                        missing[key] = []
                    missing[key].append(program)

        # Check Node
        node_dir = self.programs_dir / "node"
        for category, programs in self.NODE_CATEGORIES.items():
            category_dir = node_dir / category
            for program in programs:
                if not (category_dir / program).exists():
                    key = f"node_{category}"
                    if key not in missing:
                        missing[key] = []
                    missing[key].append(program)

        return missing


def create_workload_generator(programs_dir: Optional[Path] = None) -> WorkloadGenerator:
    """Factory function to create a WorkloadGenerator."""
    return WorkloadGenerator(programs_dir)
