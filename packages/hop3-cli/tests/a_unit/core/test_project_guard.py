# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the project-mismatch guard (ADR 042 §D14)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_cli.core.project_guard import check_project_mismatch
from hop3_cli.core.resolution import AppSource, is_cwd_rooted

if TYPE_CHECKING:
    from pathlib import Path


def _write_hop3_toml(directory: Path, app_id: str) -> None:
    """Write a minimal hop3.toml with the given [metadata].id."""
    directory.joinpath("hop3.toml").write_text(f'[metadata]\nid = "{app_id}"\n')


# ---- the four key scenarios ---------------------------------------------


def test_no_hop3_toml_no_mismatch(tmp_path: Path) -> None:
    """If CWD has no hop3.toml, the guard never fires."""
    result = check_project_mismatch(
        resolved_app="some-app",
        resolved_source="$HOP3_APP",
        resolved_kind=AppSource.ENV,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result.is_mismatch is False
    assert result.cwd_app is None
    assert result.message == ""


def test_matching_ids_no_mismatch(tmp_path: Path) -> None:
    """CWD says ``myapp`` and resolver returned ``myapp`` → no mismatch."""
    _write_hop3_toml(tmp_path, "myapp")
    result = check_project_mismatch(
        resolved_app="myapp",
        resolved_source="$HOP3_APP",
        resolved_kind=AppSource.ENV,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result.is_mismatch is False
    assert result.cwd_app == "myapp"


def test_mismatch_with_cwd_rooted_source_no_fire(tmp_path: Path) -> None:
    """
    Source kind says CWD-rooted → operator explicitly remapped this
    project to a different app name; guard must NOT fire.
    """
    _write_hop3_toml(tmp_path, "myapp")
    # `[cli].app = "myapp-alt"` is a legitimate per-project rename.
    result2 = check_project_mismatch(
        resolved_app="myapp-alt",
        resolved_source="hop3.toml [cli].app at /tmp/x",
        resolved_kind=AppSource.CLI_APP,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result2.is_mismatch is False

    # And .hop3-app file.
    result3 = check_project_mismatch(
        resolved_app="myapp-pinned",
        resolved_source=".hop3-app at /tmp/x/.hop3-app",
        resolved_kind=AppSource.DOTFILE,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result3.is_mismatch is False

    # And [metadata].id (the fallback path where CWD picks its own name).
    result4 = check_project_mismatch(
        resolved_app="myapp",
        resolved_source="hop3.toml [metadata].id at /tmp/x",
        resolved_kind=AppSource.METADATA_ID,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result4.is_mismatch is False


def test_mismatch_with_env_var_source_fires(tmp_path: Path) -> None:
    """Env var pointed elsewhere → operator likely forgot ``cd`` matters here."""
    _write_hop3_toml(tmp_path, "myapp")
    result = check_project_mismatch(
        resolved_app="other-app",
        resolved_source="$HOP3_APP",
        resolved_kind=AppSource.ENV,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result.is_mismatch is True
    assert result.cwd_app == "myapp"
    assert result.resolved_app == "other-app"
    assert "Refusing to deploy" in result.message
    assert "'other-app'" in result.message
    assert "'myapp'" in result.message


def test_is_cwd_rooted_classification() -> None:
    """
    The guard's whole contract: CWD-rooted sources never fire it; flag/env
    (and unresolved) sources can. Regression for ADR 042 dropping the two
    non-CWD app sources — the surviving set must classify correctly.
    """
    for kind in (AppSource.DOTFILE, AppSource.CLI_APP, AppSource.METADATA_ID):
        assert is_cwd_rooted(kind) is True, kind
    for kind in (AppSource.FLAG, AppSource.ENV, AppSource.UNRESOLVED):
        assert is_cwd_rooted(kind) is False, kind


def test_mismatch_with_flag_source_fires(tmp_path: Path) -> None:
    """
    ``--app other`` from inside project A → guard fires.

    FLAG is *not* CWD-rooted: an explicit ``--app`` pointing elsewhere
    is precisely the operator-mistake the guard exists to catch.
    """
    _write_hop3_toml(tmp_path, "myapp")
    result = check_project_mismatch(
        resolved_app="other-app",
        resolved_source="--app flag",
        resolved_kind=AppSource.FLAG,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result.is_mismatch is True


# ---- message format -----------------------------------------------------


def test_message_format_contains_required_pieces(tmp_path: Path) -> None:
    """
    The refusal message must include both names, the source, and both
    remediation paths exactly as the ADR spells them out.
    """
    _write_hop3_toml(tmp_path, "project-here")
    result = check_project_mismatch(
        resolved_app="elsewhere",
        resolved_source="$HOP3_APP",
        resolved_kind=AppSource.ENV,
        verb="restart",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    msg = result.message
    assert "Refusing to restart" in msg
    assert "'elsewhere'" in msg
    assert "'project-here'" in msg
    assert "(resolved app came from: $HOP3_APP)" in msg
    assert "hop3 context use" in msg
    assert "hop3 restart --force" in msg
    # The ADR's literal text demands the headline immediately precede
    # the two bullets, with the source appendix at the bottom.
    headline_idx = msg.index("Refusing to restart")
    bullet_idx = msg.index("- To restart")
    source_idx = msg.index("(resolved app came from:")
    assert headline_idx < bullet_idx < source_idx


# ---- search-upward behaviour --------------------------------------------


def test_finds_hop3_toml_in_parent_directory(tmp_path: Path) -> None:
    """The walker looks at parents until hitting the configured ``home``."""
    _write_hop3_toml(tmp_path, "rootapp")
    nested = tmp_path / "subdir" / "deeper"
    nested.mkdir(parents=True)
    result = check_project_mismatch(
        resolved_app="another",
        resolved_source="$HOP3_APP",
        resolved_kind=AppSource.ENV,
        verb="deploy",
        cwd=nested,
        home=tmp_path.parent,
    )
    assert result.is_mismatch is True
    assert result.cwd_app == "rootapp"


def test_walk_stops_at_home(tmp_path: Path) -> None:
    """A hop3.toml above ``home`` must not be picked up."""
    # Create the toml ABOVE the home boundary.
    _write_hop3_toml(tmp_path, "above-home")
    home = tmp_path / "home"
    cwd = home / "subproject"
    cwd.mkdir(parents=True)
    result = check_project_mismatch(
        resolved_app="other",
        resolved_source="$HOP3_APP",
        resolved_kind=AppSource.ENV,
        verb="deploy",
        cwd=cwd,
        home=home,
    )
    assert result.is_mismatch is False
    assert result.cwd_app is None


# ---- toml read failure modes --------------------------------------------


def test_unparseable_hop3_toml_is_skipped(tmp_path: Path) -> None:
    """Broken TOML → treat as if no metadata id; don't fire, don't crash."""
    tmp_path.joinpath("hop3.toml").write_text("not [ valid toml")
    result = check_project_mismatch(
        resolved_app="other",
        resolved_source="$HOP3_APP",
        resolved_kind=AppSource.ENV,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result.is_mismatch is False
    assert result.cwd_app is None


def test_hop3_toml_without_metadata_id_skipped(tmp_path: Path) -> None:
    """A hop3.toml that has no [metadata].id is treated as absent for guard purposes."""
    tmp_path.joinpath("hop3.toml").write_text('[build]\nbuilder = "static"\n')
    result = check_project_mismatch(
        resolved_app="other",
        resolved_source="$HOP3_APP",
        resolved_kind=AppSource.ENV,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result.is_mismatch is False
    assert result.cwd_app is None


def test_metadata_id_empty_string_ignored(tmp_path: Path) -> None:
    """An empty or whitespace-only [metadata].id is ignored."""
    tmp_path.joinpath("hop3.toml").write_text('[metadata]\nid = "   "\n')
    result = check_project_mismatch(
        resolved_app="other",
        resolved_source="$HOP3_APP",
        resolved_kind=AppSource.ENV,
        verb="deploy",
        cwd=tmp_path,
        home=tmp_path.parent,
    )
    assert result.is_mismatch is False
