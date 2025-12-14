#!/bin/bash
#
# Build and push sandbox images to GitHub Container Registry (GHCR)
#
# Usage:
#   ./scripts/build-ghcr.sh                    # Reads from .env file
#   ./scripts/build-ghcr.sh --owner myuser     # Override owner
#   ./scripts/build-ghcr.sh --help             # Show help
#
# Environment variables (can be set in .env):
#   GHCR_OWNER  - GitHub username/org (required)
#   GHCR_USER   - GitHub username for login (defaults to GHCR_OWNER)
#   GHCR_PAT    - Personal Access Token with write:packages scope (required)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default values
BUILD_PYTHON=true
BUILD_NODE=true
BUILD_LATEST=true
DRY_RUN=false

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Build and push sandbox images to GitHub Container Registry.

Options:
    --owner OWNER       GitHub username/org for GHCR (overrides GHCR_OWNER)
    --user USER         GitHub username for login (overrides GHCR_USER)
    --pat PAT           Personal Access Token (overrides GHCR_PAT)
    --python-only       Only build Python images
    --node-only         Only build Node images
    --no-latest         Skip building 'latest' tags
    --dry-run           Show what would be built without pushing
    -h, --help          Show this help message

Environment variables (can be set in .env file):
    GHCR_OWNER          GitHub username/org (required)
    GHCR_USER           GitHub username for login (defaults to GHCR_OWNER)
    GHCR_PAT            Personal Access Token with write:packages (required)

Examples:
    # Build all images using .env file
    ./scripts/build-ghcr.sh

    # Build only Python images
    ./scripts/build-ghcr.sh --python-only

    # Dry run to see what would be built
    ./scripts/build-ghcr.sh --dry-run

    # Override owner from command line
    ./scripts/build-ghcr.sh --owner bikramkgupta --pat ghp_xxx
EOF
    exit 0
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Load .env file if it exists
load_env() {
    local env_file="$PROJECT_ROOT/.env"
    if [[ -f "$env_file" ]]; then
        log_info "Loading environment from $env_file"
        # Export variables from .env, ignoring comments and empty lines
        set -a
        source <(grep -v '^#' "$env_file" | grep -v '^$' | sed 's/^/export /')
        set +a
    fi
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --owner)
                GHCR_OWNER="$2"
                shift 2
                ;;
            --user)
                GHCR_USER="$2"
                shift 2
                ;;
            --pat)
                GHCR_PAT="$2"
                shift 2
                ;;
            --python-only)
                BUILD_NODE=false
                shift
                ;;
            --node-only)
                BUILD_PYTHON=false
                shift
                ;;
            --no-latest)
                BUILD_LATEST=false
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                usage
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                ;;
        esac
    done
}

# Validate required variables
validate_env() {
    local missing=false

    if [[ -z "$GHCR_OWNER" ]]; then
        log_error "GHCR_OWNER is required. Set in .env or use --owner"
        missing=true
    fi

    if [[ -z "$GHCR_PAT" ]]; then
        log_error "GHCR_PAT is required. Set in .env or use --pat"
        missing=true
    fi

    # Default GHCR_USER to GHCR_OWNER if not set
    GHCR_USER="${GHCR_USER:-$GHCR_OWNER}"

    if [[ "$missing" == "true" ]]; then
        echo ""
        log_info "Create a .env file with:"
        echo "    GHCR_OWNER=your-github-username"
        echo "    GHCR_PAT=ghp_your_token_here"
        exit 1
    fi
}

# Setup Docker buildx
setup_buildx() {
    log_info "Setting up Docker buildx..."
    if ! docker buildx inspect sandbox-builder &>/dev/null; then
        docker buildx create --use --name sandbox-builder
    else
        docker buildx use sandbox-builder
    fi
}

# Login to GHCR
docker_login() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would login to ghcr.io as $GHCR_USER"
        return
    fi

    log_info "Logging in to ghcr.io as $GHCR_USER..."
    echo "$GHCR_PAT" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
}

# Build and push a single image
build_image() {
    local dockerfile="$1"
    local tag="$2"
    local context="$3"

    local full_tag="ghcr.io/$GHCR_OWNER/$tag"

    echo ""
    log_info "Building: $full_tag"
    log_info "  Dockerfile: $dockerfile"
    log_info "  Context: $context"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would build and push $full_tag"
        return
    fi

    docker buildx build \
        --platform linux/amd64 \
        -f "$dockerfile" \
        -t "$full_tag" \
        "$context" \
        --push

    log_info "Successfully pushed: $full_tag"
}

# Build all images
build_all() {
    local images_dir="$PROJECT_ROOT/images"

    echo ""
    echo "=========================================="
    echo "  Building Sandbox Images for GHCR"
    echo "=========================================="
    echo "  Owner: $GHCR_OWNER"
    echo "  User:  $GHCR_USER"
    echo "=========================================="
    echo ""

    # Python images
    if [[ "$BUILD_PYTHON" == "true" ]]; then
        log_info "Building Python images..."

        build_image \
            "$images_dir/python/Dockerfile.python3.12" \
            "sandbox-python:python3.12" \
            "$images_dir/python/"

        build_image \
            "$images_dir/python/Dockerfile.python3.13" \
            "sandbox-python:python3.13" \
            "$images_dir/python/"

        if [[ "$BUILD_LATEST" == "true" ]]; then
            build_image \
                "$images_dir/python/Dockerfile" \
                "sandbox-python:latest" \
                "$images_dir/python/"
        fi
    fi

    # Node images
    if [[ "$BUILD_NODE" == "true" ]]; then
        log_info "Building Node images..."

        build_image \
            "$images_dir/node/Dockerfile.node22" \
            "sandbox-node:node22" \
            "$images_dir/node/"

        build_image \
            "$images_dir/node/Dockerfile.node24" \
            "sandbox-node:node24" \
            "$images_dir/node/"

        if [[ "$BUILD_LATEST" == "true" ]]; then
            build_image \
                "$images_dir/node/Dockerfile" \
                "sandbox-node:latest" \
                "$images_dir/node/"
        fi
    fi

    echo ""
    echo "=========================================="
    log_info "All builds complete!"
    echo "=========================================="
    echo ""
    log_info "Images pushed to:"
    if [[ "$BUILD_PYTHON" == "true" ]]; then
        echo "  - ghcr.io/$GHCR_OWNER/sandbox-python:python3.12"
        echo "  - ghcr.io/$GHCR_OWNER/sandbox-python:python3.13"
        [[ "$BUILD_LATEST" == "true" ]] && echo "  - ghcr.io/$GHCR_OWNER/sandbox-python:latest"
    fi
    if [[ "$BUILD_NODE" == "true" ]]; then
        echo "  - ghcr.io/$GHCR_OWNER/sandbox-node:node22"
        echo "  - ghcr.io/$GHCR_OWNER/sandbox-node:node24"
        [[ "$BUILD_LATEST" == "true" ]] && echo "  - ghcr.io/$GHCR_OWNER/sandbox-node:latest"
    fi
    echo ""
    log_warn "Remember to make packages PUBLIC in GitHub:"
    echo "  https://github.com/$GHCR_OWNER?tab=packages"
}

# Main
main() {
    load_env
    parse_args "$@"
    validate_env
    setup_buildx
    docker_login
    build_all
}

main "$@"
