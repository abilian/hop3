# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Shared test fixtures for hop3-cli.

The autouse fixture defined here is the test-isolation contract for the
whole package: unit tests must not depend on the developer's CWD or on
``HOP3_*`` environment variables that happen to be set in the shell.
Without it, tests pick up:

- ``./.hop3-local.toml`` from whichever directory pytest was invoked in
  (the resolver reads it as context source #3);
- ``./.hop3-app`` and ``./hop3.toml`` from CWD or an ancestor (app
  resolution sources #4 and #5);
- ``$HOP3_APP``, ``$HOP3_CONTEXT``, etc. from the
  shell, all of which short-circuit the resolver chain at sources #1-2;
- ``$HOP3_DEV_MODE`` which silently switches the API URL to localhost.

Each of these has, at least once, caused a test pass-or-fail to depend
on developer machine state rather than the code under test. The fixture
forces every test into a clean room and lets individual tests opt back
in to a specific signal via their own ``monkeypatch.setenv`` /
``monkeypatch.chdir`` calls (which run after this fixture and override
its defaults).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# `stubs.py` lives in this directory and is imported as a top-level module
# (`from stubs import ...`) by tests nested under tests/ (a_unit/commands,
# a_unit/rpc). The repo-root pytest config uses --import-mode=importlib, which
# does NOT add test directories to sys.path, so a bare `import stubs` fails for
# those nested tests. This conftest is loaded before any test under tests/, so
# putting its own directory on sys.path makes `stubs` importable everywhere.
sys.path.insert(0, str(Path(__file__).parent))

# ===========================================================================
# Environment isolation fixture
# ===========================================================================

# Every HOP3_* var the CLI reads (across config.py, main.py,
# commands/flags.py, resolution.py). Add to this list when a new
# env-driven knob is introduced — keeping it complete is the whole
# point of the fixture.
_HOP3_ENV_VARS = (
    "HOP3_API_TOKEN",
    "HOP3_API_URL",
    "HOP3_APP",
    "HOP3_CONFIG_DIR",
    "HOP3_CONTEXT",
    "HOP3_DEV_HOST",
    "HOP3_DEV_MODE",
    "HOP3_NO_INPUT",
    "HOP3_VERBOSITY",
)


@pytest.fixture(autouse=True)
def _isolate_cli_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Default-isolate every test from CWD-based files and HOP3_* env vars.

    - ``chdir(tmp_path)`` so ``Path.cwd()`` lookups (``.hop3-app``,
      ``.hop3-local.toml``, ``hop3.toml`` upward walks) start in an
      empty directory.
    - Delete every known ``HOP3_*`` env var so resolver sources #1-2 are
      empty unless the test explicitly sets one.

    - point ``$HOP3_CONFIG_DIR`` at a per-test tmp dir so the config dir
      (``config.toml`` / ``servers.toml`` / ``state.toml``) — resolved through
      ``core.paths.config_dir`` — is isolated from the developer's real
      ``~/.config/hop3-cli``. Without this, any test reaching ``get_config`` /
      ``default_servers_path`` / the ADR-042 migration would read (and, for the
      migration, REWRITE/DELETE) the operator's real config.

    Individual tests can override any side by calling
    ``monkeypatch.chdir(other_path)`` or ``monkeypatch.setenv("HOP3_X", "v")``
    — those calls happen after this fixture and win.
    """
    monkeypatch.chdir(tmp_path)
    for var in _HOP3_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOP3_CONFIG_DIR", str(tmp_path / "hop3-config"))
