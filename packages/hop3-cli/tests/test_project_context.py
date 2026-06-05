# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the project-scoped `hop3 context` verbs (ADR 042 Step 3)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import tomllib
from hop3_cli.commands.local.project_context_cmd import (
    find_project_hop3_toml,
    handle_project_context,
)
from hop3_cli.core.local_overlay import (
    LOCAL_OVERLAY_FILENAME,
    read_overlay,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---- find_project_hop3_toml ----------------------------------------------


def test_find_project_hop3_toml_in_cwd(tmp_path: Path) -> None:
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "x"\n')
    assert find_project_hop3_toml(cwd=tmp_path, home=tmp_path) == (
        tmp_path / "hop3.toml"
    )


def test_find_project_hop3_toml_walks_up(tmp_path: Path) -> None:
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "x"\n')
    sub = tmp_path / "src" / "deep"
    sub.mkdir(parents=True)
    assert find_project_hop3_toml(cwd=sub, home=tmp_path) == (tmp_path / "hop3.toml")


def test_find_project_hop3_toml_missing(tmp_path: Path) -> None:
    assert find_project_hop3_toml(cwd=tmp_path, home=tmp_path) is None


# ---- hop3 context use --------------------------------------------------


def _project(tmp_path: Path, hop3_toml: str) -> Path:
    """Write a hop3.toml and return its path."""
    p = tmp_path / "hop3.toml"
    p.write_text(hop3_toml)
    return p


def _printer() -> MagicMock:
    return MagicMock()


def _config(server: str | None = None, app: str | None = None) -> MagicMock:
    """A stub Config.

    ``server`` / ``app`` model the values stashed from the global
    ``--server`` / ``--app`` flags (which parse_flags consumes before the
    subcommand runs). Default to None so handlers fall back to whatever the
    subcommand parsed locally.
    """
    config = MagicMock()
    config.get_server_override.return_value = server
    config.get_app_override.return_value = app
    return config


def test_context_use_writes_overlay(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """
[metadata]
id = "myapp"

[contexts.dev]
server = "dev"
""",
    )
    handle_project_context(
        ["use", "dev"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context == "dev"


def test_context_use_unknown_context_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(
        tmp_path,
        """
[contexts.dev]
server = "dev"
""",
    )
    with pytest.raises(SystemExit) as exc:
        handle_project_context(
            ["use", "staging"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "staging" in err
    assert "dev" in err  # the "Available" hint includes declared contexts


def test_context_use_no_contexts_declared_exits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, '[metadata]\nid = "x"\n')
    with pytest.raises(SystemExit):
        handle_project_context(
            ["use", "anything"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    err = capsys.readouterr().err
    assert "context add" in err


# ---- hop3 context list -------------------------------------------------


def test_context_list_shows_declared_blocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(
        tmp_path,
        """
[contexts.dev]
server = "dev"
app = "myapp-dev"

[contexts.prod]
server = "prod"
app = "myapp"
""",
    )
    handle_project_context(
        ["list"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    out = capsys.readouterr().out
    assert "dev" in out
    assert "prod" in out
    assert "myapp-dev" in out


def test_context_list_marks_current(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(
        tmp_path,
        """
[contexts.dev]
server = "dev"
""",
    )
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text('[current]\ncontext = "dev"\n')
    handle_project_context(
        ["list"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    out = capsys.readouterr().out
    # The asterisk marker appears next to the current context.
    assert "* dev" in out


def test_context_list_warns_on_duplicate_targets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two contexts resolving to the same (server, app) → stderr warning."""
    project = _project(
        tmp_path,
        """
[contexts.prod]
server = "prod"
app = "myapp"

[contexts.production]
server = "prod"
app = "myapp"
""",
    )
    handle_project_context(
        ["list"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    captured = capsys.readouterr()
    assert "warning" in captured.err
    assert "prod" in captured.err
    assert "production" in captured.err


def test_context_list_empty_contexts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, '[metadata]\nid = "x"\n')
    handle_project_context(
        ["list"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    out = capsys.readouterr().out
    assert "No project contexts declared" in out


# ---- hop3 context show -------------------------------------------------


def test_context_show_resolves_inherited_app(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When a context omits `app`, show displays the [metadata].id fallback."""
    project = _project(
        tmp_path,
        """
[metadata]
id = "myapp"

[contexts.dev]
server = "dev"
""",
    )
    handle_project_context(
        ["show", "dev"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    out = capsys.readouterr().out
    assert "myapp" in out  # inherited from [metadata].id


def test_context_show_env_merges_with_top_level(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Env merge: context wins on matches, top-level inherits unmatched keys."""
    project = _project(
        tmp_path,
        """
[env]
DEBUG = "true"
APP_NAME = "myapp"

[contexts.prod]
server = "prod"

[contexts.prod.env]
DEBUG = "false"
""",
    )
    handle_project_context(
        ["show", "prod"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    out = capsys.readouterr().out
    # Context wins on the matched key
    assert "DEBUG" in out
    assert "'false'" in out
    # Unmatched top-level key inherits
    assert "APP_NAME" in out


def test_context_show_domains_full_replace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Domains: context list replaces top-level entirely."""
    project = _project(
        tmp_path,
        """
[domains]
list = ["fallback.example.com"]

[contexts.prod]
server = "prod"
domains = ["prod.example.com"]
""",
    )
    handle_project_context(
        ["show", "prod"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    out = capsys.readouterr().out
    assert "prod.example.com" in out
    assert "fallback.example.com" not in out


def test_context_show_default_uses_current(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bare `show` uses the current context from .hop3-local.toml."""
    project = _project(
        tmp_path,
        """
[contexts.dev]
server = "dev"
app = "myapp-dev"
""",
    )
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text('[current]\ncontext = "dev"\n')
    handle_project_context(
        ["show"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    out = capsys.readouterr().out
    assert "(current)" in out
    assert "myapp-dev" in out


def test_context_show_unknown_context(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, '[contexts.dev]\nserver = "dev"\n')
    with pytest.raises(SystemExit):
        handle_project_context(
            ["show", "staging"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    assert "staging" in capsys.readouterr().err


# ---- hop3 context add --------------------------------------------------


def test_context_add_writes_block(tmp_path: Path) -> None:
    project = _project(tmp_path, '[metadata]\nid = "myapp"\n')
    handle_project_context(
        [
            "add",
            "dev",
            "--server",
            "dev-server",
            "--app",
            "myapp-dev",
            "--domain",
            "dev.myapp.example.com",
        ],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    data = tomllib.loads(project.read_text())
    assert data["contexts"]["dev"]["server"] == "dev-server"
    assert data["contexts"]["dev"]["app"] == "myapp-dev"
    assert data["contexts"]["dev"]["domains"] == ["dev.myapp.example.com"]


def test_context_add_server_required(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, "")
    with pytest.raises(SystemExit):
        handle_project_context(
            ["add", "dev"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    assert "--server is required" in capsys.readouterr().err


def test_context_add_duplicate_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, '[contexts.dev]\nserver = "s"\n')
    with pytest.raises(SystemExit):
        handle_project_context(
            ["add", "dev", "--server", "s"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    err = capsys.readouterr().err
    assert "already exists" in err


# ---- hop3 context remove -----------------------------------------------


def test_context_remove_deletes_block(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """
[contexts.dev]
server = "dev"

[contexts.prod]
server = "prod"
""",
    )
    handle_project_context(
        ["remove", "dev"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    data = tomllib.loads(project.read_text())
    assert "dev" not in data.get("contexts", {})
    assert "prod" in data["contexts"]


def test_context_remove_last_drops_contexts_table(tmp_path: Path) -> None:
    """Removing the only context drops the empty [contexts] table."""
    project = _project(
        tmp_path,
        """
[metadata]
id = "myapp"

[contexts.only]
server = "s"
""",
    )
    handle_project_context(
        ["remove", "only"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    data = tomllib.loads(project.read_text())
    assert "contexts" not in data
    # Other sections preserved
    assert data["metadata"]["id"] == "myapp"


def test_context_remove_warns_when_was_current(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, '[contexts.dev]\nserver = "s"\n')
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text('[current]\ncontext = "dev"\n')
    handle_project_context(
        ["remove", "dev"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    err = capsys.readouterr().err
    assert "current selection" in err


def test_context_remove_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, "")
    with pytest.raises(SystemExit):
        handle_project_context(
            ["remove", "nope"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    assert "nope" in capsys.readouterr().err


# ---- hop3 context init -------------------------------------------------


def test_context_init_creates_block_and_overlay(tmp_path: Path) -> None:
    project = _project(tmp_path, '[metadata]\nid = "myapp"\n')
    handle_project_context(
        ["init", "--server", "dev-server"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    # hop3.toml got [contexts.dev]
    data = tomllib.loads(project.read_text())
    assert data["contexts"]["dev"]["server"] == "dev-server"
    # .hop3-local.toml has current context = dev
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context == "dev"


def test_context_init_respects_name(tmp_path: Path) -> None:
    project = _project(tmp_path, "")
    handle_project_context(
        ["init", "--server", "s", "--name", "staging"],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    data = tomllib.loads(project.read_text())
    assert "staging" in data["contexts"]
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context == "staging"


def test_context_init_refuses_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, '[contexts.dev]\nserver = "old"\n')
    with pytest.raises(SystemExit):
        handle_project_context(
            ["init", "--server", "new"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    err = capsys.readouterr().err
    assert "already exists" in err


def test_context_init_reads_server_from_flag_override(tmp_path: Path) -> None:
    """`--server` is consumed by the global flag parser, so init must read it
    from the stashed config override — not from args."""
    project = _project(tmp_path, '[metadata]\nid = "myapp"\n')
    handle_project_context(
        ["init"],  # no --server here: parse_flags already ate it
        _config(server="hop3.dev"),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    data = tomllib.loads(project.read_text())
    assert data["contexts"]["dev"]["server"] == "hop3.dev"
    assert read_overlay(cwd=tmp_path, home=tmp_path).current_context == "dev"


def test_context_init_app_override_and_local_name(tmp_path: Path) -> None:
    """`--app` arrives via config override; `--name` survives in args."""
    project = _project(tmp_path, "")
    handle_project_context(
        ["init", "--name", "staging"],
        _config(server="s", app="my-app"),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    data = tomllib.loads(project.read_text())
    assert data["contexts"]["staging"]["server"] == "s"
    assert data["contexts"]["staging"]["app"] == "my-app"


def test_context_init_no_server_anywhere_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With neither a local --server nor a config override, init must refuse —
    not silently print usage as if no arguments were given."""
    project = _project(tmp_path, "")
    with pytest.raises(SystemExit):
        handle_project_context(
            ["init"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    assert "--server is required" in capsys.readouterr().err


def test_context_add_reads_server_from_flag_override(tmp_path: Path) -> None:
    """`hop3 context add <name>` reads the stripped --server from config too."""
    project = _project(tmp_path, "")
    handle_project_context(
        ["add", "prod"],  # no --server: parse_flags ate it
        _config(server="prod-server"),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    data = tomllib.loads(project.read_text())
    assert data["contexts"]["prod"]["server"] == "prod-server"


def test_context_init_end_to_end_strips_and_restores_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end through run_command_from_args: `hop3 context init --server X`.

    This is the path the unit tests skip — it exercises parse_flags (which
    strips --server) plus the main.py stash plus the handler read. It's the
    regression guard for the bug where the documented command printed usage.
    """
    from hop3_cli.config import Config  # noqa: PLC0415
    from hop3_cli.main import run_command_from_args  # noqa: PLC0415

    _project(tmp_path, '[metadata]\nid = "myapp"\n')
    monkeypatch.chdir(tmp_path)

    with (
        patch("hop3_cli.main.load_config", return_value=Config()),
        patch("hop3_cli.main._apply_aliases", side_effect=lambda args, *a, **kw: args),
    ):
        run_command_from_args(["context", "init", "--server", "hop3.dev"])

    data = tomllib.loads((tmp_path / "hop3.toml").read_text())
    assert data["contexts"]["dev"]["server"] == "hop3.dev"


# ---- Dispatcher -----------------------------------------------------------


def test_unknown_subcommand_exits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, "")
    with pytest.raises(SystemExit):
        handle_project_context(
            ["nonsense"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    err = capsys.readouterr().err
    assert "Unknown context subcommand" in err


def test_bare_context_shows_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(
        tmp_path,
        """
[contexts.dev]
server = "dev"
""",
    )
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text('[current]\ncontext = "dev"\n')
    handle_project_context(
        [],
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    out = capsys.readouterr().out
    assert "Current context: dev" in out
    assert "Subcommands" in out


# ---- Name validation (Step-3 review blocker #1) -------------------------


@pytest.mark.parametrize(
    "bad_name",
    ["has space", "2prod", "prod/eu", "default", "DEFAULT", "all", "current"],
)
def test_context_add_rejects_invalid_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bad_name: str
) -> None:
    """Names that fail the schema rules must be rejected BEFORE writing.

    Without this guard, a bad name would land in hop3.toml and only blow
    up at the next ``Hop3Config.from_file`` call.
    """
    project = _project(tmp_path, "")
    with pytest.raises(SystemExit):
        handle_project_context(
            ["add", bad_name, "--server", "s"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    assert bad_name in capsys.readouterr().err
    # The file shouldn't have been written.
    assert project.read_text() == ""


@pytest.mark.parametrize("bad_name", ["has space", "2prod", "default", "ALL"])
def test_context_init_rejects_invalid_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bad_name: str
) -> None:
    """`init --name <bad>` rejects before touching either file."""
    project = _project(tmp_path, "")
    original_contents = project.read_text()
    with pytest.raises(SystemExit):
        handle_project_context(
            ["init", "--server", "s", "--name", bad_name],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    assert bad_name in capsys.readouterr().err
    # No half-applied state.
    assert project.read_text() == original_contents
    assert not (tmp_path / LOCAL_OVERLAY_FILENAME).exists()


def test_context_init_default_name_is_valid(tmp_path: Path) -> None:
    """The default name 'dev' passes validation (regression for the deny-list)."""
    project = _project(tmp_path, "")
    handle_project_context(
        ["init", "--server", "s"],  # no --name → default "dev"
        _config(),
        _printer(),
        project_hop3=project,
        cwd=tmp_path,
        home=tmp_path,
    )
    data = tomllib.loads(project.read_text())
    assert "dev" in data["contexts"]


# ---- _resolve_view drift fix (Step-3 review blocker #2) ------------------


def test_context_show_raises_on_missing_server_field(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A block missing `server` surfaces as a focused error, not empty output.

    Matches the server-side ``Hop3Config.resolve_context`` invariant.
    Reachable via `validate=False` paths or hand-edited hop3.toml.
    """
    project = _project(
        tmp_path,
        """
[contexts.broken]
app = "x"
""",
    )
    with pytest.raises(SystemExit):
        handle_project_context(
            ["show", "broken"],
            _config(),
            _printer(),
            project_hop3=project,
            cwd=tmp_path,
            home=tmp_path,
        )
    err = capsys.readouterr().err
    assert "broken" in err
    assert "server" in err


# ---- project_has_contexts (Step-3 review integration #4) ---------------


def test_project_has_contexts_true_when_declared(tmp_path: Path) -> None:
    from hop3_cli.commands.local.project_context_cmd import (  # noqa: PLC0415
        project_has_contexts,
    )

    project = _project(tmp_path, '[contexts.dev]\nserver = "s"\n')
    assert project_has_contexts(project) is True


def test_project_has_contexts_false_when_legacy_shape(tmp_path: Path) -> None:
    """A legacy hop3.toml without [contexts] returns False — dispatcher then
    routes to global-server handler.
    """
    from hop3_cli.commands.local.project_context_cmd import (  # noqa: PLC0415
        project_has_contexts,
    )

    project = _project(
        tmp_path,
        """
[metadata]
id = "legacy"

[build]
builder = "local"
""",
    )
    assert project_has_contexts(project) is False


def test_project_has_contexts_false_on_parse_error(tmp_path: Path) -> None:
    from hop3_cli.commands.local.project_context_cmd import (  # noqa: PLC0415
        project_has_contexts,
    )

    project = _project(tmp_path, "this is not valid toml [[[")
    assert project_has_contexts(project) is False


# ---- Cross-package validator parity (drift insurance) -------------------


def test_cli_context_name_validator_matches_schema():
    """The CLI-side validator must accept/reject the same names as the schema.

    The CLI and server have independent implementations (no cross-package
    import). This test pins their agreement so a future change to the
    server-side deny-list or regex doesn't silently drift.
    """
    from hop3_cli.core.context_names import (  # noqa: PLC0415
        _CONTEXT_NAME_RE as CLI_RE,
        _RESERVED_CONTEXT_NAMES as CLI_RESERVED,
    )

    from hop3.project.schema import (  # noqa: PLC0415
        _CONTEXT_NAME_RE as SERVER_RE,
        _RESERVED_CONTEXT_NAMES as SERVER_RESERVED,
    )

    assert CLI_RESERVED == SERVER_RESERVED, (
        "Reserved-name deny-list drifted between CLI and schema. "
        "Update one to match the other."
    )
    assert CLI_RE.pattern == SERVER_RE.pattern, (
        "Context-name regex drifted between CLI and schema."
    )
