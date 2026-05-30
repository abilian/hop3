# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the migration step in the deployer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hop3_installer.common import CommandResult
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer


@pytest.fixture
def config():
    """Minimal valid DeployConfig for unit tests."""
    return DeployConfig(host="example.com", use_docker=False)


@pytest.fixture
def backend():
    """A backend mock with a configurable .run() result."""
    b = MagicMock()
    b.run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    return b


def _make_deployer(config: DeployConfig, backend) -> Deployer:
    d = Deployer(config, backend)
    # Silence log output so test runs are quiet
    d.quiet = True
    return d


class TestRunMigrations:
    """Tests for Deployer._run_migrations."""

    def test_invokes_db_upgrade_via_sudo(self, config, backend):
        """The deployer must run 'hop3-server db:upgrade' as the hop3 user."""
        d = _make_deployer(config, backend)
        assert d._run_migrations() is True

        backend.run.assert_called_once()
        cmd = backend.run.call_args.args[0]
        assert "sudo -u hop3" in cmd
        assert "db:upgrade" in cmd

    def test_failure_aborts_with_false(self, config, backend):
        """A failed migration must return False (and the caller must not restart)."""
        backend.run.return_value = CommandResult(
            returncode=1, stdout="", stderr="schema mismatch"
        )
        d = _make_deployer(config, backend)
        assert d._run_migrations() is False

    def test_skip_migrations_short_circuits(self, config, backend):
        """--skip-migrations must not invoke alembic at all."""
        config.skip_migrations = True
        d = _make_deployer(config, backend)
        assert d._run_migrations() is True
        backend.run.assert_not_called()


class TestUpdatePathsRunMigrationsBeforeRestart:
    """Each update path must run migrations before the systemctl restart.

    This is the load-bearing invariant: a failed migration must leave the
    OLD server running on the OLD schema, not the NEW server crashing
    against an OLD schema.
    """

    def _run_calls(self, backend) -> list[str]:
        return [call.args[0] for call in backend.run.call_args_list]

    def test_update_local_code_runs_migrations_then_restarts(self, config, backend):
        config.use_local_code = True
        d = _make_deployer(config, backend)
        # Stub the upload to succeed without touching the network
        d.backend.upload_dir = MagicMock(return_value=True)

        assert d._update_local_code() is True
        calls = self._run_calls(backend)
        migrate_idx = next(i for i, c in enumerate(calls) if "db:upgrade" in c)
        restart_idx = next(
            i for i, c in enumerate(calls) if "systemctl restart hop3-server" in c
        )
        assert migrate_idx < restart_idx, (
            f"migration must precede restart; got {calls!r}"
        )

    def test_features_install_does_not_reinstall_hop3_server(self, config, backend):
        """Regression: features step must not reinstall hop3-server from PyPI.

        Without --skip-package-install, every deploy that triggers
        _install_features (which is every deploy with --with set, and the
        default includes 'docker') overwrites whatever the preceding
        _update_local_code/_update_from_git/_update_from_pypi step
        installed. The symptom is `hop3 system info` reporting PyPI's
        latest stable version (e.g. 0.4.0) even after a successful
        --local deploy of newer code (e.g. 0.5.0.dev3).
        """
        config.with_features = ["docker"]
        d = _make_deployer(config, backend)

        # Stub out the upload + version-check shell-outs in _install_features
        d.backend.upload_file = MagicMock(return_value=True)
        d.backend.run_streaming = MagicMock(return_value=0)
        d._ensure_python310_plus = MagicMock(return_value="python3")
        # The installer_path property triggers bundle regeneration if stale;
        # short-circuit it to avoid running the real bundler in unit tests.
        from pathlib import Path as _Path  # noqa: PLC0415

        type(config).installer_path = property(
            lambda self: _Path("/dev/null").parent / "fake-installer.py"
        )
        # `not installer_path.exists()` is the abort condition; satisfy it
        with patch("pathlib.Path.exists", return_value=True):
            assert d._install_features() is True

        install_cmd = next(c.args[0] for c in backend.run_streaming.call_args_list)
        assert "--skip-package-install" in install_cmd, (
            "features re-run must pass --skip-package-install; otherwise "
            f"the installer's step 4 reinstalls hop3-server from PyPI. "
            f"Got: {install_cmd!r}"
        )

    def test_update_local_code_uninstalls_before_install(self, config, backend):
        """The local-code path must uninstall before installing.

        Without this, repeated --local deploys can leave a stale .dist-info
        on disk while writing new code into hop3/, so
        importlib.metadata.version() reports an old version.
        """
        config.use_local_code = True
        d = _make_deployer(config, backend)
        d.backend.upload_dir = MagicMock(return_value=True)

        assert d._update_local_code() is True
        calls = self._run_calls(backend)
        uninstall_idx = next(
            i
            for i, c in enumerate(calls)
            if "pip uninstall" in c and "hop3-server" in c
        )
        install_idx = next(
            i for i, c in enumerate(calls) if "pip install" in c and "hop3-server" in c
        )
        assert uninstall_idx < install_idx, (
            f"uninstall must precede install; got {calls!r}"
        )

    def test_update_local_code_aborts_on_migration_failure(self, config, backend):
        config.use_local_code = True

        def fake_run(cmd, **kwargs):
            if "db:upgrade" in cmd:
                return CommandResult(returncode=1, stdout="", stderr="boom")
            return CommandResult(returncode=0)

        backend.run.side_effect = fake_run
        d = _make_deployer(config, backend)
        d.backend.upload_dir = MagicMock(return_value=True)

        assert d._update_local_code() is False
        calls = self._run_calls(backend)
        assert not any("systemctl restart hop3-server" in c for c in calls), (
            "server must NOT restart if migrations failed"
        )

    def test_update_from_pypi_runs_migrations_then_restarts(self, config, backend):
        d = _make_deployer(config, backend)
        assert d._update_from_pypi() is True
        calls = self._run_calls(backend)
        migrate_idx = next(i for i, c in enumerate(calls) if "db:upgrade" in c)
        restart_idx = next(
            i for i, c in enumerate(calls) if "systemctl restart hop3-server" in c
        )
        assert migrate_idx < restart_idx

    def test_update_from_git_runs_migrations_then_restarts(self, config, backend):
        d = _make_deployer(config, backend)
        assert d._update_from_git() is True
        calls = self._run_calls(backend)
        migrate_idx = next(i for i, c in enumerate(calls) if "db:upgrade" in c)
        restart_idx = next(
            i for i, c in enumerate(calls) if "systemctl restart hop3-server" in c
        )
        assert migrate_idx < restart_idx
