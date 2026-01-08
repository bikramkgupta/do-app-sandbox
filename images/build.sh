#!/bin/bash
# Build and push sandbox container images to GHCR
#
# Usage:
#   ./build.sh [OPTIONS]
#
# Options:
#   --push          Push images to registry after building
#   --registry      Registry host (default: ghcr.io)
#   --owner         Image owner/namespace (default: GHCR_OWNER env or "bikramkgupta")
#   --tag           Image tag (default: latest)
#   --image         Build specific image only (python-worker, python-service, node-worker, node-service)
#
# Examples:
#   ./build.sh                              # Build all images locally
#   ./build.sh --push                       # Build and push all images
#   ./build.sh --image python-service       # Build only python-service image
#   ./build.sh --tag v1.0.0 --push          # Build and push with specific tag

set -e

# Default values
REGISTRY="${GHCR_REGISTRY:-ghcr.io}"
OWNER="${GHCR_OWNER:-bikramkgupta}"
TAG="latest"
PUSH=false
SPECIFIC_IMAGE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --push)
            PUSH=true
            shift
            ;;
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        --owner)
            OWNER="$2"
            shift 2
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --image)
            SPECIFIC_IMAGE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Images to build
IMAGES=(
    "sandbox-python-worker"
    "sandbox-python-service"
    "sandbox-node-worker"
    "sandbox-node-service"
)

# Filter to specific image if requested
if [[ -n "$SPECIFIC_IMAGE" ]]; then
    found=false
    for img in "${IMAGES[@]}"; do
        if [[ "$img" == "$SPECIFIC_IMAGE" || "$img" == "sandbox-$SPECIFIC_IMAGE" ]]; then
            IMAGES=("$img")
            found=true
            break
        fi
    done
    if [[ "$found" == false ]]; then
        echo "Error: Unknown image '$SPECIFIC_IMAGE'"
        echo "Available images: ${IMAGES[*]}"
        exit 1
    fi
fi

echo "=== Sandbox Image Builder ==="
echo "Registry: $REGISTRY"
echo "Owner: $OWNER"
echo "Tag: $TAG"
echo "Push: $PUSH"
echo "Images: ${IMAGES[*]}"
echo ""

# Build each image
for IMAGE_NAME in "${IMAGES[@]}"; do
    FULL_IMAGE="$REGISTRY/$OWNER/$IMAGE_NAME:$TAG"

    echo "=== Building $IMAGE_NAME ==="

    # Service images need sandbox_api copied into context
    if [[ "$IMAGE_NAME" == *"-service" ]]; then
        # Create temp build context
        BUILD_DIR=$(mktemp -d)
        cp -r "$SCRIPT_DIR/$IMAGE_NAME"/* "$BUILD_DIR/"
        cp -r "$SCRIPT_DIR/sandbox_api" "$BUILD_DIR/"

        docker build -t "$FULL_IMAGE" "$BUILD_DIR"

        rm -rf "$BUILD_DIR"
    else
        docker build -t "$FULL_IMAGE" "$SCRIPT_DIR/$IMAGE_NAME"
    fi

    echo "Built: $FULL_IMAGE"

    if [[ "$PUSH" == true ]]; then
        echo "Pushing $FULL_IMAGE..."
        docker push "$FULL_IMAGE"
        echo "Pushed: $FULL_IMAGE"
    fi

    echo ""
done

echo "=== Build Complete ==="
