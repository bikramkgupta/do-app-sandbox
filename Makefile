# =============================================================================
# DO App Sandbox - Development Makefile
# =============================================================================
# Run `make help` to see available commands
#
# For test commands, see tests/Makefile:
#   cd tests && make help
# =============================================================================

.PHONY: help install lint format type-check security check fix clean

# =============================================================================
# Help
# =============================================================================

help:
	@echo ""
	@echo "DO App Sandbox - Development Commands"
	@echo "======================================"
	@echo ""
	@echo "Development:"
	@echo "  make install       Install dependencies"
	@echo "  make lint          Run Ruff linter"
	@echo "  make format        Format code with Ruff"
	@echo "  make type-check    Run mypy type checker"
	@echo "  make security      Run pip-audit security scan"
	@echo "  make check         Run all checks (lint + type-check)"
	@echo "  make fix           Auto-fix linting issues and format"
	@echo "  make clean         Remove build artifacts"
	@echo ""
	@echo "Testing:"
	@echo "  cd tests && make help    See test commands"
	@echo ""
	@echo "Quick test examples:"
	@echo "  cd tests && make test-setup     # Create shared sandboxes"
	@echo "  cd tests && make test-git       # Run git tests"
	@echo "  cd tests && make test-teardown  # Cleanup"
	@echo ""

# =============================================================================
# Development
# =============================================================================

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

clean:
	rm -rf build/ dist/ *.egg-info/ .mypy_cache/ .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
