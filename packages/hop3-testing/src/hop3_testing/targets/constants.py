# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Constants for deployment targets."""

from __future__ import annotations

import os
import tempfile
from functools import cache

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
# Matches hop3-installer's DOCKER_IMAGE: the test target should be the
# distribution the platform is developed and deployed against.
DEFAULT_DOCKER_IMAGE = "ubuntu:24.04"
DEFAULT_READY_IMAGE = "hop3-ready:latest"

# SSH-related defaults
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "hop3"
DEFAULT_SSH_ROOT_USER = "root"

#: The server-side CLI on a Hop3 box (the installer's VENV_DIR is /home/hop3/venv).
HOP3_SERVER_BIN = "/home/hop3/venv/bin/hop3-server"

#: Where a Hop3 box keeps its apps, and its enabled uWSGI vassals.
HOP3_APPS_ROOT = "/home/hop3/apps"
HOP3_UWSGI_ENABLED = "/home/hop3/uwsgi-enabled"

#: Touched in an app's directory just before its workers start
#: (``hop3.run.spawn.AppLauncher.WORKERS_STARTED_MARKER``; a test pins the two).
WORKERS_STARTED_MARKER = ".hop3-workers-started"

# Test environment secrets (NOT for production use)
E2E_TEST_SECRET_KEY = "e2e-test-secret-key-do-not-use-in-production"


# Ambient HOP3_* vars that steer the hop3 CLI's target/auth resolution AHEAD of
# the HOP3_API_URL/HOP3_API_TOKEN the harness sets explicitly — HOP3_DEV_MODE is
# get_api_url()'s #1 priority, so a single leaked value silently redirects a
# deploy to the wrong server/credential (a 401). We strip them from the env of
# every hop3 CLI call so the harness is hermetic: it talks to the target it
# deployed, with the token it fetched, regardless of the (possibly polluted)
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
    # Retired remote-target selectors (ADR 043): stripped so a leaked value can
    # never redirect a harness hop3/hop3-test call. A target comes from an
    # explicit --host / $HOP3_HOST only.
    "HOP3_TEST_HOST",
    "HOP3_TEST_SERVER",
)


def hermetic_cli_env() -> dict[str, str]:
    """
    A copy of the process environment with the HOP3_* steering vars removed.

    The caller then sets the explicit HOP3_API_URL / HOP3_API_TOKEN it wants
    honored. Use this instead of ``os.environ.copy()`` for any hop3 CLI
    invocation so ambient HOP3_* vars can't override the harness's target.
    """
    env = dict(os.environ)
    for var in _CLI_STEERING_ENV_VARS:
        env.pop(var, None)
    return env


@cache
def hermetic_cli_cwd() -> str:
    """
    A directory with NO ``hop3.toml`` in its ancestry — the CWD for every
    harness ``hop3`` subprocess.

    The harness always targets apps explicitly (``--app NAME``), so the CLI
    needs no project context from the working directory. But the CLI resolves a
    project — and runs the project-mismatch guard — relative to its CWD. So a
    stray ``hop3.toml`` in the directory the test runner launched from (e.g. the
    repo root) makes ``hop3 deploy`` / ``app destroy`` refuse with a project
    mismatch. Running from a dedicated empty dir makes the harness hermetic
    w.r.t. CWD, the same way ``hermetic_cli_env`` makes it hermetic w.r.t. env.
    ``@cache`` so every call shares one empty directory.
    """
    return tempfile.mkdtemp(prefix="hop3-cli-cwd-")
