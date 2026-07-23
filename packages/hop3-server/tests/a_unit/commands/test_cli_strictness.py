# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Regression tests for fail-loud CLI behavior.

Two commands used to silently do the wrong thing:
- `app list` ignored stray positional args, so `hop3 apps status` looked
  identical to `hop3 apps` (the trailing token was dropped).
- `config live` fell back to database values (mislabeled as live) when it
  could not inspect the running app, making it indistinguishable from
  `config show`.

Both must now fail loudly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.commands.app import DeployCmd, RestartCmd, _resolve_app
from hop3.commands.apps import AppsCmd
from hop3.commands.config import LiveCmd

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App


def test_app_list_rejects_stray_args(db_session: Session):
    """`app list` (a.k.a. `apps`) must reject extra positional args."""
    cmd = AppsCmd(db_session=db_session)
    with pytest.raises(ValueError, match="takes no arguments"):
        cmd.call("status")


def test_app_list_accepts_no_args(db_session: Session):
    """The valid form still works."""
    cmd = AppsCmd(db_session=db_session)
    result = cmd.call()
    assert isinstance(result, list)


def test_config_live_fails_loud_when_not_running(db_session: Session, test_app: App):
    """`config live` must not silently fall back to stored config values."""
    cmd = LiveCmd(db_session=db_session)
    # The fixture app is not actually running, so live inspection can't
    # succeed — this must raise rather than return DB values.
    with pytest.raises(ValueError, match="live environment"):
        cmd.call("--app", "testapp")


# ---- C9: app-scoped commands reject stray args; deploy keeps its source dir ----


def test_resolve_app_rejects_stray_arg_by_default():
    """A no-positional app command rejects a stray token (e.g. `restart --bogus`)."""
    with pytest.raises(ValueError, match="Unrecognized argument"):
        _resolve_app(("--app", "myapp", "--bogus"))


def test_resolve_app_allow_extra_keeps_trailing_positional():
    """Commands that DO take a positional (deploy <dir>, ping <path>) opt out."""
    assert _resolve_app(("--app", "myapp", "/tmp/src"), allow_extra=True) == (
        "myapp",
        ["/tmp/src"],
    )


def test_app_restart_rejects_stray_args(db_session: Session):
    """`app restart --app x --bogus` must fail loud, not silently plain-restart."""
    with pytest.raises(ValueError, match="Unrecognized argument"):
        RestartCmd(db_session=db_session).call("--app", "testapp", "--bogus")


def test_deploy_tolerates_source_dir_positional(db_session: Session):
    """
    `hop3 deploy --app X <dir>` forwards the source-dir positional, which the
    server ignores (source arrives as the uploaded tarball). Deploy must NOT
    reject it as a stray arg — the C9 over-reach that broke every e2e deploy.

    An invalid app name makes validation fire immediately after arg-resolution,
    so we prove the trailing positional got PAST ``_resolve_app`` without
    running a real deploy.
    """
    with pytest.raises(ValueError) as exc:
        DeployCmd(db_session=db_session).call("--app", "Bad Name", "/tmp/src")
    assert "Unrecognized argument" not in str(exc.value)
