# DO App Sandbox - Development Makefile
# Run `make help` to see available commands

.PHONY: help lint format type-check security check fix test test-unit install clean

help:
	@echo "Available commands:"
	@echo "  make install     - Install dependencies"
	@echo "  make lint        - Run Ruff linter"
	@echo "  make format      - Format code with Ruff"
	@echo "  make type-check  - Run mypy type checker"
	@echo "  make security    - Run pip-audit security scan"
	@echo "  make check       - Run all checks (lint + type-check + security)"
	@echo "  make fix         - Auto-fix linting issues and format"
	@echo "  make test        - Run all tests"
	@echo "  make test-unit   - Run unit tests only"
	@echo "  make clean       - Remove build artifacts"

install:
	uv sync --extra dev

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

type-check:
	uv run mypy src/

security:
	uv run pip-audit

check: lint type-check
	@echo "All checks passed!"

fix:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

test:
	uv run pytest tests/ -v

test-unit:
	uv run pytest tests/unit/ -v

clean:
	rm -rf build/ dist/ *.egg-info/ .mypy_cache/ .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
