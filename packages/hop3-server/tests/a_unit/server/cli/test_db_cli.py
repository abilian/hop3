# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for server-side CLI database commands (hop3-server db:*)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hop3.server.cli.db import (
    DbCmd,
    DbCurrentCmd,
    DbStampCmd,
    DbUpgradeCmd,
    _alembic_config,
)


class TestAlembicConfig:
    """Tests for the _alembic_config() helper."""

    def test_resolves_to_bundled_ini(self):
        """The helper should find the alembic.ini that ships with hop3."""
        cfg = _alembic_config()
        ini_path = Path(cfg.config_file_name)
        assert ini_path.name == "alembic.ini"
        assert ini_path.exists()

    def test_script_location_resolves_to_alembic_dir(self):
        """The bundled .ini's script_location must point at a real dir."""
        cfg = _alembic_config()
        script_location = cfg.get_main_option("script_location")
        assert script_location is not None
        assert Path(script_location).is_dir()
        assert (Path(script_location) / "env.py").exists()

    def test_missing_ini_raises(self):
        """If alembic.ini is missing we should fail loudly, not silently."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            pytest.raises(FileNotFoundError),
        ):
            _alembic_config()


class TestDbGroupCommand:
    """The group command itself (DbCmd) has no run method."""

    def test_name(self):
        assert DbCmd.name == "db"

    def test_no_run_method(self):
        """The group's docstring is shown via the Help system; no run()."""
        assert not hasattr(DbCmd, "run") or DbCmd.run is object.__init__  # safety


class TestDbUpgradeCmd:
    """
    Tests for db:upgrade.

    These exercise revision forwarding and error handling. The pre-Alembic
    adoption step is mocked out here (it touches a real database); its
    behavior is covered by tests/b_integration/test_db_adoption.py.
    """

    @pytest.fixture(autouse=True)
    def _no_adopt(self):
        """Stub the DB-adoption step so these stay pure unit tests."""
        with patch("hop3.server.cli.db._adopt_unstamped_db"):
            yield

    def test_name(self):
        assert DbUpgradeCmd.name == "db:upgrade"

    def test_default_revision_is_head(self):
        """Without --revision, upgrade head is the default."""
        with patch("alembic.command.upgrade") as mock_upgrade:
            DbUpgradeCmd().run()
            args, _ = mock_upgrade.call_args
            assert args[1] == "head"

    def test_custom_revision_passed_through(self):
        """A specific revision should be forwarded to alembic.command.upgrade."""
        with patch("alembic.command.upgrade") as mock_upgrade:
            DbUpgradeCmd().run(revision="961bfd2ecce5")
            args, _ = mock_upgrade.call_args
            assert args[1] == "961bfd2ecce5"

    def test_adopt_runs_before_upgrade(self):
        """
        A pre-Alembic DB must be stamped (adopted) BEFORE upgrade runs,
        otherwise upgrade replays from base and hits 'duplicate column'.
        """
        calls: list[str] = []
        with (
            patch(
                "hop3.server.cli.db._adopt_unstamped_db",
                side_effect=lambda _cfg: calls.append("adopt"),
            ),
            patch(
                "alembic.command.upgrade",
                side_effect=lambda _cfg, _rev: calls.append("upgrade"),
            ),
        ):
            DbUpgradeCmd().run()
        assert calls == ["adopt", "upgrade"]

    def test_failure_exits_nonzero(self):
        """A migration error must abort with exit code 1, not pass silently."""
        with patch("alembic.command.upgrade", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc:
                DbUpgradeCmd().run()
            assert exc.value.code == 1

    def test_unstamped_db_hint_emitted(self, capsys):
        """
        When the error smells like a pre-alembic DB, point at db:stamp.

        A truly unstamped DB has no current revision, so _orphan_db_revision
        returns None; mock it so the test exercises the unstamped branch and
        does not depend on any ambient hop3.db the orphan check would inspect.
        """
        err = RuntimeError("duplicate column name: error_message")
        with (
            patch("alembic.command.upgrade", side_effect=err),
            patch("hop3.server.cli.db._orphan_db_revision", return_value=None),
            pytest.raises(SystemExit),
        ):
            DbUpgradeCmd().run()
        stderr = capsys.readouterr().err
        assert "db:stamp head" in stderr
        assert "metadata.create_all()" in stderr

    def test_generic_failure_does_not_emit_hint(self, capsys):
        """A normal migration error should NOT suggest db:stamp (would be bad advice)."""
        err = RuntimeError("some unrelated transient failure")
        with (
            patch("alembic.command.upgrade", side_effect=err),
            patch("hop3.server.cli.db._orphan_db_revision", return_value=None),
            pytest.raises(SystemExit),
        ):
            DbUpgradeCmd().run()
        stderr = capsys.readouterr().err
        assert "db:stamp" not in stderr

    def test_orphan_revision_hint_emitted(self, capsys):
        """
        A DB stamped at a revision this code lacks gets the orphan hint —
        names the revision, points at recovery, and does NOT auto-recover.
        """
        err = RuntimeError("Can't locate revision identified by 'c7d4e8f1a2b9'")
        with (
            patch("alembic.command.upgrade", side_effect=err),
            patch(
                "hop3.server.cli.db._orphan_db_revision",
                return_value="c7d4e8f1a2b9",
            ),
            pytest.raises(SystemExit),
        ):
            DbUpgradeCmd().run()
        stderr = capsys.readouterr().err
        assert "c7d4e8f1a2b9" in stderr
        assert "not part" in stderr  # explains the divergence
        assert "db:stamp head" in stderr  # offers a recovery path
        # The unstamped/pre-Alembic advice must NOT also fire (wrong diagnosis).
        assert "predate Alembic" not in stderr

    def test_add_arguments_declares_revision(self):
        """The --revision flag must be declared with a default of head."""
        import argparse  # ruff:ignore[import-outside-top-level]

        parser = argparse.ArgumentParser()
        DbUpgradeCmd().add_arguments(parser)
        ns = parser.parse_args([])
        assert ns.revision == "head"
        ns = parser.parse_args(["--revision", "abc123"])
        assert ns.revision == "abc123"


class TestDbCurrentCmd:
    """Tests for db:current."""

    def test_name(self):
        assert DbCurrentCmd.name == "db:current"

    def test_invokes_alembic_current(self):
        with patch("alembic.command.current") as mock_current:
            DbCurrentCmd().run()
            assert mock_current.call_count == 1

    def test_failure_exits_nonzero(self):
        with patch("alembic.command.current", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc:
                DbCurrentCmd().run()
            assert exc.value.code == 1


class TestDbStampCmd:
    """Tests for db:stamp."""

    def test_name(self):
        assert DbStampCmd.name == "db:stamp"

    def test_revision_passed_through(self):
        with patch("alembic.command.stamp") as mock_stamp:
            DbStampCmd().run(revision="head")
            args, _ = mock_stamp.call_args
            assert args[1] == "head"

    def test_failure_exits_nonzero(self):
        with patch("alembic.command.stamp", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc:
                DbStampCmd().run(revision="head")
            assert exc.value.code == 1

    def test_add_arguments_requires_revision(self):
        """db:stamp without a revision argument should fail at parse time."""
        import argparse  # ruff:ignore[import-outside-top-level]

        parser = argparse.ArgumentParser()
        DbStampCmd().add_arguments(parser)
        with pytest.raises(SystemExit):
            parser.parse_args([])
