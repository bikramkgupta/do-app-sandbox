# =============================================================================
# DO App Sandbox - Test Makefile
# =============================================================================
# Run from the tests/ directory: cd tests && make help
#
# Quick Start:
#   make test-setup      # Create shared sandboxes (~3 min)
#   make test-git        # Run git tests (fast with shared sandbox)
#   make test-teardown   # Cleanup when done
# =============================================================================

.PHONY: help
.PHONY: test test-unit test-api test-integration test-functional test-one
.PHONY: test-git test-service test-snapshot test-hibernate test-pool test-workflow
.PHONY: test-setup test-teardown test-status
.PHONY: ci-test ci-integration ci-quick ci-api

# Default TEST path for test-one
TEST ?= .

# =============================================================================
# Help
# =============================================================================

help:
	@echo ""
	@echo "DO App Sandbox - Test Commands"
	@echo "=============================="
	@echo ""
	@echo "Test Setup/Teardown:"
	@echo "  make test-setup    Create shared sandboxes, write to .env (~3 min)"
	@echo "  make test-teardown Delete shared sandboxes, clean .env"
	@echo "  make test-status   Show shared sandbox health status"
	@echo ""
	@echo "Run Tests (by category):"
	@echo "  make test          Run all tests (unit + integration + functional)"
	@echo "  make test-unit     Run unit tests only (no cloud, fast)"
	@echo "  make test-api      Run API tests (needs shared service sandbox)"
	@echo "  make test-integration  Run integration tests"
	@echo "  make test-functional   Run functional tests"
	@echo ""
	@echo "Run Specific Tests:"
	@echo "  make test-one TEST=integration/test_git_checkout.py  Run specific file"
	@echo "  make test-one TEST=integration::TestClass::method    Run specific method"
	@echo ""
	@echo "Test Shortcuts:"
	@echo "  make test-git      Git checkout tests"
	@echo "  make test-service  Service mode tests"
	@echo "  make test-snapshot Snapshot tests"
	@echo "  make test-hibernate Hibernation tests"
	@echo "  make test-pool     Pool basic tests"
	@echo "  make test-workflow Workflow tests"
	@echo ""
	@echo "CI Pipelines:"
	@echo "  make ci-test       Full: setup -> all tests -> teardown"
	@echo "  make ci-integration Integration: setup -> integration -> teardown"
	@echo "  make ci-quick      Quick: setup -> unit + smoke -> teardown"
	@echo "  make ci-api        API: setup -> api tests -> teardown"
	@echo ""
	@echo "Example Workflow:"
	@echo "  make test-setup          # Start session (creates sandboxes)"
	@echo "  make test-git            # Run tests (uses shared sandbox)"
	@echo "  make test-service        # Run more tests"
	@echo "  make test-teardown       # End session (cleanup)"
	@echo ""

# =============================================================================
# Test Setup/Teardown
# =============================================================================

test-setup:
	@echo "Creating shared test sandboxes..."
	cd .. && uv run python tests/scripts/test_setup.py
	@echo "Shared sandboxes ready. Run 'make test-status' to verify."

test-teardown:
	@echo "Cleaning up shared sandboxes..."
	cd .. && uv run python tests/scripts/test_teardown.py
	@echo "Cleanup complete."

test-status:
	@cd .. && uv run python tests/scripts/test_status.py

# =============================================================================
# Run Tests by Category
# =============================================================================

test:
	cd .. && uv run pytest tests/ -v --ignore=tests/stress --ignore=tests/benchmarks --ignore=tests/perf

test-unit:
	cd .. && uv run pytest tests/unit/ -v

test-api:
	cd .. && uv run pytest tests/api/ -v

test-integration:
	cd .. && uv run pytest tests/integration/ -v --tb=short

test-functional:
	cd .. && uv run python tests/functional/run_all.py

# =============================================================================
# Run Specific Test
# =============================================================================

test-one:
	@echo "Running: $(TEST)"
	cd .. && uv run pytest tests/$(TEST) -v -s

# =============================================================================
# Test Shortcuts
# =============================================================================

test-git:
	cd .. && uv run pytest tests/integration/test_git_checkout.py -v -s

test-service:
	cd .. && uv run pytest tests/integration/test_service_mode.py -v -s

test-snapshot:
	cd .. && uv run pytest tests/integration/test_snapshots.py -v -s

test-hibernate:
	cd .. && uv run pytest tests/integration/test_hibernation.py -v -s

test-pool:
	cd .. && uv run pytest tests/integration/test_pool_basic.py -v -s

test-workflow:
	cd .. && uv run pytest tests/integration/test_workflow.py -v -s

test-manager-snapshot:
	cd .. && uv run pytest tests/integration/test_manager_snapshots.py -v -s

test-pty:
	cd .. && uv run pytest tests/integration/test_pty_leak.py -v -s

# =============================================================================
# CI Pipelines
# =============================================================================

ci-test:
	@echo "CI Full Test Pipeline"
	@echo "====================="
	$(MAKE) test-setup
	$(MAKE) test-unit
	$(MAKE) test-integration || ($(MAKE) test-teardown && exit 1)
	$(MAKE) test-functional || ($(MAKE) test-teardown && exit 1)
	$(MAKE) test-teardown
	@echo "CI Pipeline Complete!"

ci-integration:
	@echo "CI Integration Test Pipeline"
	@echo "============================"
	$(MAKE) test-setup
	$(MAKE) test-integration || ($(MAKE) test-teardown && exit 1)
	$(MAKE) test-teardown
	@echo "CI Integration Pipeline Complete!"

ci-quick:
	@echo "CI Quick Test Pipeline"
	@echo "======================"
	$(MAKE) test-setup
	$(MAKE) test-unit
	$(MAKE) test-workflow || ($(MAKE) test-teardown && exit 1)
	$(MAKE) test-teardown
	@echo "CI Quick Pipeline Complete!"

ci-api:
	@echo "CI API Test Pipeline"
	@echo "===================="
	$(MAKE) test-setup
	$(MAKE) test-api || ($(MAKE) test-teardown && exit 1)
	$(MAKE) test-teardown
	@echo "CI API Pipeline Complete!"
