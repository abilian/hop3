# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The server installer migrates hop3-server's database before restarting it.

Only `hop3-deploy-server` ran `hop3-server db:upgrade`. The install one-liner,
the documented way to upgrade a server, installed the new package and restarted
hop3-server on it, against a schema the new code did not match.
"""

from __future__ import annotations

import pytest
from hop3_installer.common import CommandError
from hop3_installer.server_installer import installer, python
from hop3_installer.server_installer.config import ServerInstallerConfig

STEPS = (
    "install_system_deps",
    "create_user_and_group",
    "fix_s3_env_ownership",
    "_install_optional_toolchains",
    "create_virtual_environment",
    "_install_package_step",
    "run_hop3_setup",
    "migrate_database",
)


@pytest.fixture
def ran(monkeypatch) -> list[str]:
    """Replace each step of `_run_critical_steps` with a recorder."""
    calls: list[str] = []
    for name in STEPS:
        monkeypatch.setattr(
            installer, name, lambda *_a, _name=name, **_k: calls.append(_name) or True
        )
    return calls


def test_the_database_is_migrated_after_the_package_is_installed(ran) -> None:
    assert installer._run_critical_steps("arch", ServerInstallerConfig())

    # Last of steps 1-5: step 7, which restarts hop3-server, comes after.
    assert ran[-1] == "migrate_database"
    assert ran.index("_install_package_step") < ran.index("migrate_database")


def test_skip_migrations_skips_it(ran) -> None:
    config = ServerInstallerConfig(skip_migrations=True)

    assert installer._run_critical_steps("arch", config)

    assert "migrate_database" not in ran


def test_the_migration_runs_db_upgrade_as_hop3(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        python, "run_as_hop3", lambda argv, check=False: calls.append((argv, check))
    )

    python.migrate_database()

    [(argv, check)] = calls
    assert argv[-1] == "db:upgrade"
    assert argv[0].endswith("/bin/hop3-server")
    assert check, "a failed migration must abort the install"


def test_a_failed_migration_aborts_the_install(monkeypatch) -> None:
    def fails(argv, check=False):
        raise CommandError(
            cmd=argv, returncode=1, stderr="Error: migration failed", stdout=""
        )

    monkeypatch.setattr(python, "run_as_hop3", fails)

    with pytest.raises(CommandError, match="db:upgrade") as raised:
        python.migrate_database()

    # The installer prints this output when it reports the failure.
    assert "migration failed" in raised.value.stderr
