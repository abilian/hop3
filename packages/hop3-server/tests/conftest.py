# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Root conftest for hop3-server tests - provides deployment target fixtures."""

from __future__ import annotations

import json
import os
import re

import pytest
from filelock import FileLock
from hop3_testing.catalog import Catalog
from hop3_testing.targets import (
    DeploymentConfig,
    DeploymentTarget,
    DockerConfig,
    DockerTarget,
    RemoteConfig,
    RemoteTarget,
)
from hop3_testing.targets.helpers import find_project_root

from hop3.orm import reset_session_factory_cache
from hop3.server.security.rate_limit import AUTH_RATE_LIMITER

# Import fixtures from di_fixtures.py to make them available to all tests
from .di_fixtures import di_container  # ruff:ignore[unused-import]

# Provide a stable session secret so create_app() doesn't warn about a generated
# key during tests. The warning (asgi.py) is a production-only concern; tests
# don't need a persistent secret. Set before any test module imports the ASGI
# app (none of the imports above pull it in, verified). setdefault keeps any
# real value a developer may have exported.
os.environ.setdefault("HOP3_SESSION_SECRET", "test-session-secret-not-for-production")


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch):
    """
    Use the minimum bcrypt work factor in tests.

    Password hashing is intentionally slow in production (~0.3s/hash at the
    default cost). Tests only exercise the hash/verify *roundtrip*, not the work
    factor, so force the minimum (4 rounds) — this alone cuts ~10s off the
    auth/user/admin integration suite. ``checkpw`` reads the cost from the hash,
    so verification is unaffected.
    """
    import bcrypt  # ruff:ignore[import-outside-top-level] - localized to this perf fixture

    original_gensalt = bcrypt.gensalt
    monkeypatch.setattr(
        bcrypt, "gensalt", lambda *args, **kwargs: original_gensalt(rounds=4)
    )


@pytest.fixture(autouse=True)
def _fast_pbkdf2(monkeypatch):
    """
    Cap PBKDF2 iterations in tests.

    Credential encryption derives its Fernet key with 600k PBKDF2 iterations
    (OWASP 2026 baseline) — ~0.15s per ``CredentialEncryption()``. Tests exercise
    the encrypt/decrypt roundtrip and scheme dispatch, not the iteration count
    (that is pinned separately against the ``SCHEME_V2_ITERATIONS`` constant, which
    this leaves untouched), so cap the actual work. Both encrypt and decrypt derive
    through this one primitive, so keys stay consistent. Same idea as ``_fast_bcrypt``.
    """
    import hashlib  # ruff:ignore[import-outside-top-level] - localized to this perf fixture

    real_pbkdf2 = hashlib.pbkdf2_hmac

    def cheap(hash_name, password, salt, iterations, dklen=None):
        return real_pbkdf2(hash_name, password, salt, min(iterations, 1000), dklen)

    monkeypatch.setattr(hashlib, "pbkdf2_hmac", cheap)


# 1. Add command-line options to pytest
def pytest_addoption(parser):
    """Adds custom command-line options for test configuration."""
    # Options for the 'remote' target
    parser.addoption(
        "--host", action="store", help="Remote target hostname (for --target=remote)"
    )
    parser.addoption(
        "--ssh-key", action="store", help="Path to SSH key for remote target"
    )
    # Options for the 'docker' target
    parser.addoption(
        "--keep-target",
        action="store_true",
        default=False,
        help="Keep Docker target running after tests",
    )
    parser.addoption(
        "--force-rebuild",
        action="store_true",
        default=False,
        help="Force rebuild of Docker image without layer cache",
    )
    # Options for nix tests
    parser.addoption(
        "--run-nix",
        action="store_true",
        default=False,
        help="Run tests for Nix-based apps (requires Nix installed on target)",
    )


#: Addon types that are NOT installer features. PostgreSQL is always installed,
#: and `--with postgres` is rejected as an unknown feature.
_ADDONS_ALWAYS_PRESENT = frozenset({"postgres", "postgresql"})

#: Where the e2e fixture apps live (platform fixtures, not the app catalog).
_FIXTURE_APP_DIRS = ("apps/test-apps-procfile", "apps/test-apps-nix")


def _declared_addon_features() -> list[str]:
    """
    Installer features (`--with`) for every addon the fixture apps declare.

    Derived, not hardcoded: the apps' own `[[addons]]` blocks are the source of
    truth, so adding a test app that needs mysql provisions mysql instead of
    failing on a target that could never have satisfied it. Deriving them only
    to *skip* the affected tests would be the silent skip the platform rules
    forbid — the target is ours to provision.
    """
    root = find_project_root()
    wanted: set[str] = set()
    for rel in _FIXTURE_APP_DIRS:
        for toml in (root / rel).glob("*/hop3.toml"):
            text = toml.read_text()
            for block in re.findall(
                r"^\[\[addons\]\](.*?)(?=^\[|\Z)", text, re.DOTALL | re.MULTILINE
            ):
                m = re.search(r'^\s*type\s*=\s*"([^"]+)"', block, re.MULTILINE)
                if m and m.group(1) not in _ADDONS_ALWAYS_PRESENT:
                    wanted.add(m.group(1))
    return sorted(wanted)


# 2. Create a session-scoped fixture for the deployment target
@pytest.fixture(scope="session")
def deployment_target(request, tmp_path_factory):
    """
    Manages the lifecycle of the deployment target for the entire test session.
    Starts the target before tests run and stops it after they complete.

    Supports pytest-xdist parallel execution by sharing a single container
    across all workers using a lock file.
    """
    keep_target = request.config.getoption("--keep-target")
    host = request.config.getoption("--host")

    # Check if running under pytest-xdist
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    is_xdist = worker_id != "master"

    target: DeploymentTarget

    if host:
        remote_config = RemoteConfig(
            host=host,
            ssh_key=request.config.getoption("--ssh-key"),
        )
        target_name = "remote"
        target = RemoteTarget(remote_config)
        # Remote targets don't need special xdist handling
        try:
            print(f"Starting deployment target '{target_name}' for test session...")
            target.start()
            yield target
        finally:
            if not keep_target:
                print(f"Stopping deployment target '{target_name}'...")
                target.stop()
            else:
                print(
                    f"Keeping deployment target '{target_name}' running as requested."
                )
        return

    # Docker target with xdist support
    # Deploy Hop3 from local code to the container
    docker_config = DockerConfig(
        container_name="hop3-server-test",
    )
    # Deploy Hop3 from local source code, WITH the backing services the test
    # apps declare. Installing none of them meant every app carrying an
    # `[[addons]]` block that isn't postgres failed the deploy on a reason the
    # target could never satisfy — `redis-cli: No such file or directory` for
    # 155-flask-redis, missing MinIO credentials for 150-flask-s3.
    deployment_config = DeploymentConfig(
        source="local",
        clean=False,
        verbose=False,
        features=_declared_addon_features(),
    )

    if is_xdist:
        # Running under pytest-xdist - share container across workers
        root_tmp = tmp_path_factory.getbasetemp().parent
        lock_file = root_tmp / "deployment_target.lock"
        info_file = root_tmp / "deployment_target.json"

        # Use filelock for coordination (built into pytest-xdist)
        with FileLock(str(lock_file)):
            if info_file.exists():
                # Another worker already started the container - reuse it
                info_data = json.loads(info_file.read_text())
                print(f"Worker {worker_id}: Reusing shared deployment target...")
                reuse_config = DockerConfig(
                    container_name=info_data.get("container_name", "hop3-server-test"),
                    reuse_container=True,
                )
                target = DockerTarget(reuse_config)
                target.start()
                yield target
                # Don't stop - let the master worker handle cleanup
                return
            else:
                # First worker - start the container and share info
                print(f"Worker {worker_id}: Starting shared deployment target...")
                target = DockerTarget(docker_config, deployment=deployment_config)
                target.start()
                # Save connection info for other workers
                info = target._info
                assert info is not None
                info_data = {
                    "container_name": docker_config.container_name,
                    "ssh_port": info.ssh_port,
                    "http_base": info.http_base,
                    "api_url": info.api_url,
                    "ssh_key": info.ssh_key,
                }
                info_file.write_text(json.dumps(info_data))
                yield target
                # Only first worker cleans up
                if not keep_target:
                    print(f"Worker {worker_id}: Stopping shared deployment target...")
                    target.stop()
                return

    # Not running under xdist - normal single-process behavior
    target_name = "docker"
    target = DockerTarget(docker_config, deployment=deployment_config)

    try:
        print(f"Starting deployment target '{target_name}' for test session...")
        target.start()
        yield target
    finally:
        if not keep_target:
            print(f"Stopping deployment target '{target_name}'...")
            target.stop()
        else:
            print(f"Keeping deployment target '{target_name}' running as requested.")


# 3. Create a fixture for the test catalog
@pytest.fixture(scope="session")
def test_catalog():
    """Provides a Catalog instance for accessing test definitions."""
    try:
        root = find_project_root()
    except RuntimeError:
        root = None
    catalog = Catalog(root)
    catalog.scan()
    return catalog


# 4. Reset session factory cache before each test to ensure test isolation
@pytest.fixture(autouse=True)
def reset_session_factory():
    """
    Reset session factory cache before each test to prevent database state pollution.

    This ensures that each test gets a fresh database connection and prevents
    tests from accidentally sharing database state through the session factory cache.
    """
    reset_session_factory_cache()
    yield
    reset_session_factory_cache()


# 5. Reset the shared auth rate limiter before each test
@pytest.fixture(autouse=True)
def reset_auth_rate_limiter():
    """
    Give every test a fresh rate-limit budget.

    `AUTH_RATE_LIMITER` is module-level and now covers both the web login form
    and the RPC `auth get-token` command, so without this the sixth
    login-attempting test in a run would fail because of the five before it —
    an order-dependent result, and one that would read as a bug in whichever
    test happened to be sixth.
    """
    AUTH_RATE_LIMITER.reset()
    yield
    AUTH_RATE_LIMITER.reset()
