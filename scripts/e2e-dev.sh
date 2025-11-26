#!/bin/bash
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
#
# E2E development helper script
#
# Usage:
#   ./scripts/e2e-dev.sh              # Run all e2e tests
#   ./scripts/e2e-dev.sh -k "flask"   # Run tests matching "flask"
#   ./scripts/e2e-dev.sh -x           # Stop on first failure
#   ./scripts/e2e-dev.sh -n 4         # Run with 4 parallel workers
#   ./scripts/e2e-dev.sh --force-rebuild  # Force rebuild Docker image (no layer cache)

set -e

E2E_DIR="packages/hop3-server/tests/d_e2e"
CONTAINER_NAME="hop3-e2e-dev"

# Default options
PYTEST_ARGS=()
FORCE_REBUILD=false
PARALLEL=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force-rebuild)
            FORCE_REBUILD=true
            shift
            ;;
        -n|--parallel)
            PARALLEL="$2"
            shift 2
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# Build pytest command
CMD="uv run pytest"

if [ "$FORCE_REBUILD" = true ]; then
    CMD="$CMD --force-rebuild"
fi

if [ -n "$PARALLEL" ]; then
    CMD="$CMD -n $PARALLEL"
fi

# Always keep target running for faster subsequent runs
CMD="$CMD --keep-target $E2E_DIR"

if [ ${#PYTEST_ARGS[@]} -gt 0 ]; then
    CMD="$CMD ${PYTEST_ARGS[*]}"
fi

echo "Running: $CMD"
$CMD

echo ""
echo "Tips:"
echo "  - Container is kept running for faster subsequent runs"
echo "  - Docker layer caching speeds up rebuilds when only code changes"
echo "  - Use --force-rebuild to ignore Docker cache entirely"
echo "  - Use -n 4 to run tests in parallel"
echo "  - Use -k 'pattern' to filter tests"
echo "  - To stop the container: docker stop hop3-e2e-dev"
