# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared test fixtures for hop3-cli.

The autouse fixture defined here is the test-isolation contract for the
whole package: unit tests must not depend on the developer's CWD or on
``HOP3_*`` environment variables that happen to be set in the shell.
Without it, tests pick up:

- ``./.hop3-local.toml`` from whichever directory pytest was invoked in
  (the resolver reads it as context source #3);
- ``./.hop3-app`` and ``./hop3.toml`` from CWD or an ancestor (app
  resolution sources #4 and #5);
- ``$HOP3_APP``, ``$HOP3_SERVER``, ``$HOP3_CONTEXT``, etc. from the
  shell, all of which short-circuit the resolver chain at sources #1-2;
- ``$HOP3_DEV_MODE`` which silently switches the API URL to localhost;
- the developer's real ``~/.config/hop3-cli/{config.toml,servers.toml}``
  — both are discovered via ``platformdirs.user_config_dir`` (not a
  ``HOP3_*`` var), so the registry read in ``resolve_app`` / ``resolve_server``
  (source #8 and the server host/single-server fallbacks) leaks real
  ``[servers]`` records into otherwise-mocked tests. Redirecting
  ``XDG_CONFIG_HOME`` to an empty tmp dir closes that hole.

Each of these has, at least once, caused a test pass-or-fail to depend
on developer machine state rather than the code under test. The fixture
forces every test into a clean room and lets individual tests opt back
in to a specific signal via their own ``monkeypatch.setenv`` /
``monkeypatch.chdir`` calls (which run after this fixture and override
its defaults).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

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
    "HOP3_SERVER",
    "HOP3_VERBOSITY",
)


@pytest.fixture(autouse=True)
def _isolate_cli_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Default-isolate every test from CWD-based files and HOP3_* env vars.

    - ``chdir(tmp_path)`` so ``Path.cwd()`` lookups (``.hop3-app``,
      ``.hop3-local.toml``, ``hop3.toml`` upward walks) start in an
      empty directory.
    - Delete every known ``HOP3_*`` env var so resolver sources #1-2 are
      empty unless the test explicitly sets one.
    - Point ``XDG_CONFIG_HOME`` at an empty tmp dir so ``platformdirs``
      resolves the CLI config dir (``config.toml`` + ``servers.toml``)
      under tmp instead of the developer's real ``~/.config/hop3-cli``.

    Individual tests can override any side by calling
    ``monkeypatch.chdir(other_path)`` or ``monkeypatch.setenv("HOP3_X", "v")``
    — those calls happen after this fixture and win.
    """
    monkeypatch.chdir(tmp_path)
    for var in _HOP3_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    # Redirect platformdirs' config-dir discovery (config.toml + servers.toml)
    # to an empty per-test location. Without this, the server registry read
    # in resolve_app/resolve_server picks up the developer's real servers.toml.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config-home"))
