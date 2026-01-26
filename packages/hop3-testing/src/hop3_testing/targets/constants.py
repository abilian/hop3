# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Constants for deployment targets."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt

# HTTP status codes that indicate a server is responding (not just connection errors)
# These mean the server is running, even if the specific endpoint returns an error.
HEALTHY_STATUS_CODES: frozenset[str] = frozenset({
    "200",  # OK
    "301",  # Moved Permanently
    "302",  # Found (redirect)
    "303",  # See Other
    "307",  # Temporary Redirect
    "308",  # Permanent Redirect
    "404",  # Not Found (server responding, route not found)
})

# Health check command to run on target servers
# Returns HTTP status code or '000' on connection failure
HEALTH_CHECK_COMMAND = (
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
)

# Default timeouts (in seconds)
DEFAULT_HEALTH_CHECK_TIMEOUT = 120
DEFAULT_READY_IMAGE_HEALTH_TIMEOUT = 60
DEFAULT_COMMAND_TIMEOUT = 300

# Docker-related defaults
DEFAULT_CONTAINER_NAME = "hop3-test"
DEFAULT_DOCKER_IMAGE = "ubuntu:24.04"
DEFAULT_READY_IMAGE = "hop3-ready:latest"

# SSH-related defaults
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "hop3"
DEFAULT_SSH_ROOT_USER = "root"

# Test environment secrets (NOT for production use)
E2E_TEST_SECRET_KEY = "e2e-test-secret-key-do-not-use-in-production"
E2E_TEST_USERNAME = "e2e-test-user"


def create_test_token(
    username: str = E2E_TEST_USERNAME, expires_hours: int = 24
) -> str:
    """Create a JWT token for E2E testing.

    This creates a valid JWT token using the E2E test secret key.
    The token is valid for the specified duration and has authenticated scope.

    Args:
        username: Username to embed in token (default: e2e-test-user)
        expires_hours: Hours until token expires (default: 24)

    Returns:
        A valid JWT token string
    """
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=expires_hours)

    payload = {
        "sub": username,
        "scopes": ["authenticated", "admin"],
        "iat": now,
        "exp": expiry,
        "jti": secrets.token_urlsafe(16),
    }

    return jwt.encode(payload, E2E_TEST_SECRET_KEY, algorithm="HS256")
