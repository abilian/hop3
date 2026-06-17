# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""ADR-036 P2.2/P7: `env show --sources` and `app logs --build`.

`env show --sources` absorbs the old `app env` (Source column); `app logs
--build` absorbs the old `app build-logs`. Both old commands are kept hidden
(back-compat) and still execute.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from hop3.commands.app import BuildLogsCmd, LogsCmd, _build_log_response
from hop3.commands.config import SetCmd, ShowCmd
from hop3.core.credentials import get_credential_encryptor
from hop3.orm import App, EnvVar
from hop3.orm.addon_credential import AddonCredential

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session


def _table(items: list[dict]) -> dict | None:
    return next((i for i in items if i["t"] == "table"), None)


@pytest.mark.integration
class TestEnvShowSources:
    def test_sources_flag_labels_addon_vs_config(self, db_session: Session):
        app = App(name="srcapp", hostname="s.example.com", port=8000)
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)

        # DATABASE_URL comes from an addon; FOO is a plain config var.
        db_session.add(EnvVar(app_id=app.id, name="FOO", value="bar"))
        db_session.add(EnvVar(app_id=app.id, name="DATABASE_URL", value="postgres://x"))
        encryptor = get_credential_encryptor()
        db_session.add(
            AddonCredential(
                app_id=app.id,
                addon_type="postgres",
                addon_name="db",
                encrypted_data=encryptor.encrypt({"DATABASE_URL": "postgres://x"}),
            )
        )
        db_session.commit()

        items = ShowCmd(db_session=db_session).call("srcapp", "--sources")
        table = _table(items)
        assert table is not None
        assert table["headers"] == ["Source", "Key", "Value"]
        by_key = {row[1]: row[0] for row in table["rows"]}
        assert by_key["DATABASE_URL"] == "addon"
        assert by_key["FOO"] == "config"

    def test_set_and_show_accept_the_app_flag(self, db_session: Session):
        """ADR 036 D5: the app is the `--app` flag, never a positional. The
        reported bug — `env set --app X KEY=VALUE` rejected because the KEY=VALUE
        was mistaken for the app — must work, and `env show --app X` must read it
        back (the LogsCmd/EnvCmd/ShowCmd positional-spec gap)."""
        app = App(name="flagapp", hostname="f.example.com", port=8002)
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)

        SetCmd(db_session=db_session).call(
            "--app", "flagapp", "SENTRY_DSN=https://k@o44322.ingest.us.sentry.io/451"
        )
        db_session.commit()

        table = _table(ShowCmd(db_session=db_session).call("--app", "flagapp"))
        assert table is not None
        keys = {row[0] for row in table["rows"]}
        assert "SENTRY_DSN" in keys

    def test_without_sources_is_two_columns(self, db_session: Session):
        app = App(name="plainapp", hostname="p.example.com", port=8001)
        db_session.add(app)
        db_session.commit()
        db_session.add(EnvVar(app_id=app.id, name="FOO", value="bar"))
        db_session.commit()

        table = _table(ShowCmd(db_session=db_session).call("plainapp"))
        assert table["headers"] == ["Key", "Value"]


class TestBuildLogs:
    def test_build_log_response_reads_file(self, tmp_path: Path):
        (tmp_path / "log").mkdir()
        (tmp_path / "log" / "build.log").write_text("step 1\nstep 2\n")
        app = MagicMock(app_path=tmp_path)

        items = _build_log_response(app, "myapp")
        assert "step 1" in items[0]["text"]

    def test_build_log_response_missing_file(self, tmp_path: Path):
        app = MagicMock(app_path=tmp_path)
        items = _build_log_response(app, "myapp")
        assert "No build logs" in items[0]["text"]

    def test_logs_has_build_flag_and_build_logs_is_hidden(self):
        assert "build" in LogsCmd._arg_spec
        assert BuildLogsCmd.hidden is True
