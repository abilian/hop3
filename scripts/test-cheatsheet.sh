#!/bin/bash
# Test script based on notes/testing-cheat-sheet.md
# Runs hop3-test commands, echoing each before execution
# Stops on first failure

set -e  # Exit on first failure

# Configuration
HOST="hop3.dev"
BRANCH="new-test-runner"

# Colors
BLUE='\033[1;34m'
NC='\033[0m' # No Color

# Helper function to echo and run commands
run() {
    echo ""
    echo -e "${BLUE}==========================================${NC}"
    echo -e "${BLUE}Running: $*${NC}"
    echo -e "${BLUE}==========================================${NC}"
    "$@"
}

echo "=============================================="
echo "Hop3 Test Runner Validation Script"
echo "Host: $HOST"
echo "Branch: $BRANCH"
echo "=============================================="

# -----------------------------------------------------------------------------
# System Testing (Docker)
# -----------------------------------------------------------------------------

echo ""
echo ">>> SYSTEM TESTING (DOCKER) <<<"

# Deploy local code to Docker and test (keep container for reuse test)
run hop3-test system --docker --keep

# Reuse existing deployment (skip deploy)
run hop3-test system --docker --reuse

# Deploy from git branch (this will replace the container)
run hop3-test system --docker --deploy-from git --branch "$BRANCH"

# Deploy from PyPI (not yet available)
# run hop3-test system --docker --deploy-from pypi

# Clean install (remove existing)
run hop3-test system --docker --clean

# Test mode: ci (more thorough)
run hop3-test system --docker --mode ci

# Generate HTML report
run hop3-test system --docker --report html

# -----------------------------------------------------------------------------
# System Testing (SSH)
# -----------------------------------------------------------------------------

echo ""
echo ">>> SYSTEM TESTING (SSH) <<<"

# Remote server via SSH (keep for reuse test)
run hop3-test system --ssh --host "$HOST" --keep

# Reuse existing deployment on remote
run hop3-test system --ssh --host "$HOST" --reuse

# Deploy from git branch to remote (needs --clean since previous was local)
run hop3-test system --ssh --host "$HOST" --deploy-from git --branch "$BRANCH" --clean

# Deploy from PyPI to remote (not yet available)
# run hop3-test system --ssh --host "$HOST" --deploy-from pypi

# Clean install on remote
run hop3-test system --ssh --host "$HOST" --clean

# -----------------------------------------------------------------------------
# App Testing
# -----------------------------------------------------------------------------

echo ""
echo ">>> APP TESTING <<<"

# Build the ready image first
run hop3-test build-ready-image

# Test all apps
run hop3-test apps

# Test specific app
run hop3-test apps 010-flask-pip-wsgi

# Test by category
run hop3-test apps --category python

# Against remote server
run hop3-test apps --target remote --host "$HOST"

# -----------------------------------------------------------------------------
# Listing and Inspecting Tests
# -----------------------------------------------------------------------------

echo ""
echo ">>> LISTING AND INSPECTING <<<"

# List all tests
run hop3-test list

# Filter by category
run hop3-test list --category deployment

# Filter by tier
run hop3-test list --tier fast

# Show test details
run hop3-test show 010-flask-pip-wsgi

# JSON output
run hop3-test list --format json

# -----------------------------------------------------------------------------
# Package Validation
# -----------------------------------------------------------------------------

echo ""
echo ">>> PACKAGE VALIDATION <<<"

# Validate an app package (using a test app as example)
run hop3-test package apps/test-apps/010-flask-pip-wsgi

# -----------------------------------------------------------------------------
# Building Docker Images
# -----------------------------------------------------------------------------

echo ""
echo ">>> BUILDING DOCKER IMAGES <<<"

# Build ready image (pre-installed Hop3)
run hop3-test build-ready-image

# Build with custom tag
run hop3-test build-ready-image --tag hop3-test:validation

# Build test image (for system tests)
run hop3-test build-test-image

echo ""
echo "=============================================="
echo "All tests completed successfully!"
echo "=============================================="
