# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The DOCKER_CONFIG the e2e fixtures hand to subprocesses must still reach the daemon.

The copy strips the credential helpers (so no keychain prompt) but kept
``currentContext`` without the ``contexts/`` directory it resolves through; on
any machine running Docker under a named context (OrbStack, Colima, Docker
Desktop) every ``docker`` CLI call then failed with "context not found", and
``hop3-deploy-server`` said "Docker is not available" while the SDK-driven
tests in the same session passed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from hop3_testing.pytest_plugin import write_docker_config

if TYPE_CHECKING:
    from pathlib import Path

_REAL_CONFIG = {
    "credsStore": "osxkeychain",
    "credHelpers": {"ghcr.io": "osxkeychain"},
    "currentContext": "orbstack",
    "auths": {"registry.example.com": {"auth": "dXNlcjpwYXNz"}},
}


def _real_docker_dir(tmp_path: Path) -> Path:
    real = tmp_path / "home" / ".docker"
    (real / "contexts" / "meta" / "abc").mkdir(parents=True)
    (real / "contexts" / "meta" / "abc" / "meta.json").write_text("{}")
    (real / "config.json").write_text(json.dumps(_REAL_CONFIG))
    return real


def test_strips_credential_helpers_and_keeps_the_rest(tmp_path: Path) -> None:
    real = _real_docker_dir(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    write_docker_config(cfg, real)

    written = json.loads((cfg / "config.json").read_text())
    assert "credsStore" not in written
    assert "credHelpers" not in written
    assert written["currentContext"] == "orbstack"
    assert written["auths"] == _REAL_CONFIG["auths"]


def test_context_resolves_through_the_copied_config(tmp_path: Path) -> None:
    real = _real_docker_dir(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    write_docker_config(cfg, real)

    meta = cfg / "contexts" / "meta" / "abc" / "meta.json"
    assert meta.is_file(), "the CLI reads currentContext's endpoint from here"
    assert (cfg / "contexts").resolve() == (real / "contexts").resolve()


def test_no_docker_config_at_all(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    write_docker_config(cfg, tmp_path / "nowhere")

    assert json.loads((cfg / "config.json").read_text()) == {}
    assert not (cfg / "contexts").exists()
