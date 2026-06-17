# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for fail-loud CLI behavior.

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
