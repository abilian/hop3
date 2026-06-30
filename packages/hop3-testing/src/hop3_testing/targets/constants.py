# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Constants for deployment targets."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

# SECURITY: production-mode interlock. Mirrors the shape used by
# DockerDeployBackend (see notes/security.md §3.3.3) — refuse to load
# this module when MODE=production so the hardcoded
# E2E_TEST_SECRET_KEY below cannot reach a production deploy by
# accident. hop3-testing is a developer tool and should never be
# imported in a production-mode process; if it is, that's the bug.
if os.environ.get("MODE", "").strip().lower() in {"production", "prod"}:
    msg = (
        "hop3_testing.targets.constants imports the E2E test signing "
        "key (E2E_TEST_SECRET_KEY) and must not be used with "
        "MODE=production. Unset MODE or use a non-production value "
        "for development/test workflows."
    )
    raise RuntimeError(msg)

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
DEFAULT_DOCKER_IMAGE = "debian:bookworm"
DEFAULT_READY_IMAGE = "hop3-ready:latest"

# SSH-related defaults
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "hop3"
DEFAULT_SSH_ROOT_USER = "root"

# Test environment secrets (NOT for production use)
E2E_TEST_SECRET_KEY = "e2e-test-secret-key-do-not-use-in-production"
E2E_TEST_USERNAME = "e2e-test-user"


def create_test_token(
    username: str = E2E_TEST_USERNAME,
    expires_hours: int = 24,
    secret_key: str = E2E_TEST_SECRET_KEY,
) -> str:
    """Create a JWT token for E2E testing.

    Creates a valid JWT signed with ``secret_key`` — which MUST be the key the
    target server validates with, or the server rejects the token. For a server
    the harness started with ``E2E_TEST_SECRET_KEY`` (Docker), the default is
    correct; for a real install (which generates its own key), pass the key read
    from the server (see ``helpers.read_server_secret_key``). This is what lets
    the harness authenticate for real instead of relying on ``HOP3_UNSAFE``.

    Args:
        username: Username to embed in token (default: e2e-test-user)
        expires_hours: Hours until token expires (default: 24)
        secret_key: HS256 signing key (default: the E2E test key)

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

    return jwt.encode(payload, secret_key, algorithm="HS256")


# Ambient HOP3_* vars that steer the hop3 CLI's target/auth resolution AHEAD of
# the HOP3_API_URL/HOP3_API_TOKEN the harness sets explicitly — HOP3_DEV_MODE is
# get_api_url()'s #1 priority, so a single leaked value silently redirects a
# deploy to the wrong server/credential (a 401). We strip them from the env of
# every hop3 CLI call so the harness is hermetic: it talks to the target it
# deployed, with the token it minted, regardless of the (possibly polluted)
# environment it was launched in — e.g. the testlab worker's app-runtime env,
# which a clean developer shell doesn't have. (Same class as the demo cli_env
# strip and audit finding C4.)
_CLI_STEERING_ENV_VARS = (
    "HOP3_API_TOKEN",
    "HOP3_API_URL",
    "HOP3_APP",
    "HOP3_CONFIG_DIR",
    "HOP3_CONTEXT",
    "HOP3_DEV_HOST",
    "HOP3_DEV_MODE",
)


def hermetic_cli_env() -> dict[str, str]:
    """A copy of the process environment with the HOP3_* steering vars removed.

    The caller then sets the explicit HOP3_API_URL / HOP3_API_TOKEN it wants
    honored. Use this instead of ``os.environ.copy()`` for any hop3 CLI
    invocation so ambient HOP3_* vars can't override the harness's target.
    """
    env = dict(os.environ)
    for var in _CLI_STEERING_ENV_VARS:
        env.pop(var, None)
    return env
