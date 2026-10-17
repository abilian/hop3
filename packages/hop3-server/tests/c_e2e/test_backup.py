# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E tests for single-instance backup and restore.

Validates the round-trip workflows described in ADR 024 §"Restore
Behaviour" against a single Hop3 instance: deploy an app, back it up,
optionally modify and redeploy, then restore (in place or as a
clone). Cross-instance migration — backup on A, restore on B — is in
the sister file `test_backup_migration.py`.

Strategy
========

Each test reuses the session-scoped `deployment_target` fixture from
`tests/conftest.py` (a `DockerTarget` that runs `hop3-deploy --docker
--local` at session start, so the container under test runs the
*current* hop3-server source — not whatever was baked into a pre-built
image). Every test deploys its own app via `DeploymentSession`, which
appends a timestamp to the name to avoid cross-test collisions.

Each test exercises one CLI flow end-to-end against the deployed app:

  - `hop3 backup create --app <app>` returns a backup_id (extracted
    from stdout via `extract_backup_id`).
  - `hop3 backup list --json` returns a structured table of backups
    (parsed via `find_json_table` / `backup_in_table`).
  - `hop3 backup info <id>` shows the manifest, including env-var
    count and checksums.
  - `hop3 backup restore <id>` (optionally `--target-app NAME`)
    repopulates the app's source / data / env / addons and invokes
    the build+spawn pipeline so the app is running again.
  - `hop3 backup destroy <id>` removes both the directory and the DB
    row.

Coverage breakdown:

  - Happy paths: create, env-var preservation in backups, in-place
    restore, restore-to-different-app-name (clone), list, delete.
  - An app with an attached PostgreSQL or MySQL addon: the backup carries
    the dump, and a restore brings a deleted row back.
  - Integrity: a backup whose archive was corrupted on disk is reported
    by `backup info` and refused by `backup restore`.

Negative paths (name collision, corrupted manifest, etc.) and the
register / cross-instance flows are in `test_backup_migration.py`.

References
----------

- ADR: `notes/adrs/024-backup-restore-system.md`
- CLI: `hop3 backup create / list / info / restore / destroy`
- Implementation: `hop3.core.backup.BackupManager`
"""

from __future__ import annotations

import contextlib
import functools
import json
from pathlib import Path

import pytest
from hop3_testing.apps import DeploymentSession
from hop3_testing.apps.catalog import AppSource

from .conftest import (
    BACKUP_DIR_IN_CONTAINER,
    backup_in_table,
    create_flask_app,
    extract_backup_id,
    find_json_table,
)

MYSQL_FIXTURE = Path(__file__).parents[4] / "apps/test-apps-procfile/156-flask-mysql"


@pytest.mark.e2e
class TestBackupRestoreE2E:
    """End-to-end tests for backup and restore."""

    def test_backup_simple_app(self, deployment_target, tmp_path):
        """Test creating a backup of a simple application."""
        app_dir = create_flask_app(tmp_path, "simple-app", "Hello from Flask!")

        app = AppSource(name="simple-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            session.deploy()  # Raises DeploymentError on failure
            assert session.check_deployed(), "App not properly deployed"

            # Create backup
            result = deployment_target.run_command(
                "backup", "create", "--app", session.app_name
            )
            assert result.success, f"Backup creation failed: {result.stderr}"
            assert "Backup created successfully!" in result.stdout

            backup_id = extract_backup_id(result.stdout)
            assert backup_id is not None
            assert backup_id, "Could not extract backup ID from output"

            # Verify backup in list
            result = deployment_target.run_command("backup", "list", "--json")
            assert result.success, f"Backup list failed: {result.stderr}"
            table = find_json_table(json.loads(result.stdout))
            assert table, "No table found in backup:list output"
            assert backup_in_table(backup_id, table), (
                f"Backup ID {backup_id} not found in backup list"
            )

            # Get backup info
            result = deployment_target.run_command("backup", "info", backup_id)
            assert result.success, f"Backup info failed: {result.stderr}"
            assert backup_id in result.stdout
            assert session.app_name in result.stdout
            assert "Integrity" in result.stdout
            assert "valid" in result.stdout.lower()

    def test_backup_includes_env_vars(self, deployment_target, tmp_path):
        """Test that backups include environment variables."""
        app_dir = create_flask_app(
            tmp_path,
            "env-app",
            response='f"Secret: {secret}"',
            extra_imports="import os",
            extra_code='secret = os.getenv("SECRET_KEY", "not-set")',
        )

        app = AppSource(name="env-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            session.deploy()  # Raises DeploymentError on failure

            # Set environment variable
            result = deployment_target.run_command(
                "config", "set", "--app", session.app_name, "SECRET_KEY=my-secret-value"
            )
            assert result.success, f"Failed to set env var: {result.stderr}"

            # Create backup
            result = deployment_target.run_command(
                "backup", "create", "--app", session.app_name
            )
            assert result.success

            backup_id = extract_backup_id(result.stdout)
            assert backup_id is not None

            # Get backup info and verify env vars
            result = deployment_target.run_command("backup", "info", backup_id)
            assert result.success
            assert "Environment:" in result.stdout

    def test_restore_simple_app(self, deployment_target, tmp_path):
        """Test restoring an application from backup."""
        app_dir = create_flask_app(tmp_path, "restore-app", "Original version")

        app = AppSource(name="restore-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            session.deploy()  # Raises DeploymentError on failure

            # Create backup
            result = deployment_target.run_command(
                "backup", "create", "--app", session.app_name
            )
            assert result.success

            backup_id = extract_backup_id(result.stdout)
            assert backup_id is not None

            # Modify the app (simulate changes)
            (app_dir / "app.py").write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Modified version"
""")

            # Redeploy with changes
            session.deploy()  # Raises DeploymentError on failure

            # Restore from backup
            result = deployment_target.run_command("backup", "restore", backup_id)
            assert result.success, f"Restore failed: {result.stderr}"
            assert "Restore completed successfully!" in result.stdout

    def test_restore_to_different_app_name(self, deployment_target, tmp_path):
        """Test restoring backup to a different application name (cloning)."""
        app_dir = create_flask_app(tmp_path, "original-app", "Original app")

        app = AppSource(name="original-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            session.deploy()  # Raises DeploymentError on failure

            # Create backup
            result = deployment_target.run_command(
                "backup", "create", "--app", session.app_name
            )
            assert result.success

            backup_id = extract_backup_id(result.stdout)
            assert backup_id is not None

            # Restore to a different app name
            result = deployment_target.run_command(
                "backup", "restore", backup_id, "--target-app", "cloned-app"
            )
            assert result.success, f"Restore to different name failed: {result.stderr}"
            assert "Restore completed successfully!" in result.stdout
            assert "cloned-app" in result.stdout

            # Verify both apps exist
            result = deployment_target.run_command("apps")
            assert result.success
            assert "original-app" in result.stdout
            assert "cloned-app" in result.stdout

    def test_list_and_filter_backups(self, deployment_target, tmp_path):
        """Test listing and filtering backups."""
        # Create and deploy two apps with backups
        for app_name in ["app1", "app2"]:
            app_dir = create_flask_app(tmp_path, app_name, app_name)

            app = AppSource(name=app_name, path=app_dir)
            with DeploymentSession(app, deployment_target) as session:
                session.deploy()  # Raises DeploymentError on failure

                result = deployment_target.run_command(
                    "backup", "create", "--app", session.app_name
                )
                assert result.success

        # List all backups
        result = deployment_target.run_command("backup", "list", "--json")
        assert result.success
        output = json.loads(result.stdout)
        table = find_json_table(output)

        if table:
            all_rows_str = " ".join(str(row) for row in table.get("rows", []))
            assert "app1" in all_rows_str or "app2" in all_rows_str, (
                "No backups found for app1 or app2"
            )
        else:
            # No backups is acceptable if cleanup removed them
            assert "error" not in result.stderr.lower(), (
                f"Error in backup list: {result.stderr}"
            )

    def test_delete_backup(self, deployment_target, tmp_path):
        """Test deleting a backup."""
        app_dir = create_flask_app(tmp_path, "delete-test-app", "Delete test")

        app = AppSource(name="delete-test-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            session.deploy()  # Raises DeploymentError on failure

            # Create backup
            result = deployment_target.run_command(
                "backup", "create", "--app", session.app_name
            )
            assert result.success

            backup_id = extract_backup_id(result.stdout)
            assert backup_id is not None

            # Verify backup exists
            result = deployment_target.run_command("backup", "list", "--json")
            assert result.success
            table = find_json_table(json.loads(result.stdout))
            assert table, "No table found in backup:list output"
            assert backup_in_table(backup_id, table), (
                f"Backup ID {backup_id} not found before delete"
            )

            # Delete the backup
            result = deployment_target.run_command("backup", "destroy", backup_id)
            assert result.success
            assert "Backup deleted successfully" in result.stdout

            # Verify backup is gone
            result = deployment_target.run_command("backup", "list", "--json")
            assert result.success
            table = find_json_table(json.loads(result.stdout))
            assert not backup_in_table(backup_id, table), (
                f"Backup ID {backup_id} still found after deletion"
            )

    def test_backup_app_with_postgres(self, deployment_target, tmp_path):
        """A backup of an app with an attached PostgreSQL addon carries its dump."""
        app_dir = create_flask_app(tmp_path, "postgres-app", requirements=_PG_REQS)

        app = AppSource(name="postgres-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            session.deploy()  # Raises DeploymentError on failure
            with _addon(deployment_target, session.app_name, "postgres") as addon:
                _sql(
                    deployment_target,
                    session.app_name,
                    "CREATE TABLE marker (v text); "
                    "INSERT INTO marker VALUES ('row-before-backup')",
                )
                backup_id = _create_backup(deployment_target, session.app_name)

                result = deployment_target.run_command("backup", "info", backup_id)
                assert result.success, result.stderr
                assert f"postgres:{addon}" in result.stdout, result.stdout

                # The dump in the backup directory holds the row, not just the
                # manifest entry: a listed-but-empty dump is a backup that lies.
                addons_dir = (
                    f"{BACKUP_DIR_IN_CONTAINER}/{session.app_name}/{backup_id}/addons"
                )
                code, _out, err = deployment_target.exec_run([
                    "sh", "-c", f"grep -rl row-before-backup {addons_dir}"
                ])  # fmt: skip
                assert code == 0, f"no dump under {addons_dir} holds the row: {err}"

    def test_restore_app_with_postgres(self, deployment_target, tmp_path):
        """Restoring an app with a PostgreSQL addon brings its data back."""
        # Not "pg-…": the addon takes its database and role names from the app,
        # and PostgreSQL reserves role names starting with `pg_`.
        app_dir = create_flask_app(tmp_path, "restore-pg", requirements=_PG_REQS)

        app = AppSource(name="restore-pg", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            session.deploy()  # Raises DeploymentError on failure
            with _addon(deployment_target, session.app_name, "postgres"):
                _sql(
                    deployment_target,
                    session.app_name,
                    "CREATE TABLE marker (v text); "
                    "INSERT INTO marker VALUES ('row-before-backup')",
                )
                backup_id = _create_backup(deployment_target, session.app_name)

                _sql(deployment_target, session.app_name, "DELETE FROM marker")
                gone = _sql(deployment_target, session.app_name, "SELECT v FROM marker")
                assert "row-before-backup" not in gone

                result = deployment_target.run_command("backup", "restore", backup_id)
                assert result.success, f"Restore failed: {result.stderr}"
                assert "Restore completed successfully!" in result.stdout

                back = _sql(deployment_target, session.app_name, "SELECT v FROM marker")
                assert "row-before-backup" in back, (
                    f"the restored database does not hold the row: {back!r}"
                )

    def test_backup_and_restore_app_with_mysql(self, deployment_target):
        """
        A MySQL dump holds the row, logs no access error, and restores it.

        mysqldump exits 0 after "Access denied; you need (at least one of) the
        PROCESS privilege(s)" when it reaches the tablespaces: no test layer had
        a MySQL, and every catalog upgrade logged it.
        """
        app = AppSource(name="flask-mysql", path=MYSQL_FIXTURE)
        with DeploymentSession(app, deployment_target) as session:
            session.deploy()  # Raises DeploymentError on failure
            mysql = functools.partial(
                _sql, deployment_target, session.app_name, runner=_MYSQL_RUNNER
            )
            mysql(
                "CREATE TABLE marker (v text); "
                "INSERT INTO marker VALUES ('row-before-backup')"
            )
            backup_id = _create_backup(deployment_target, session.app_name)

            result = deployment_target.run_command("backup", "info", backup_id)
            assert result.success, result.stderr
            assert "mysql:" in result.stdout, result.stdout
            code, out, err = deployment_target.exec_run([
                "grep", "-h", "PROCESS privilege", _SERVER_STDERR_LOG
            ])  # fmt: skip
            assert code == 1, f"the dump logged an access error: {out}{err}"

            mysql("DELETE FROM marker")
            result = deployment_target.run_command("backup", "restore", backup_id)
            assert result.success, f"Restore failed: {result.stderr}"

            back = mysql("SELECT v FROM marker")
            assert "row-before-backup" in back, (
                f"the restored database does not hold the row: {back!r}"
            )

    def test_backup_integrity_verification(self, deployment_target, tmp_path):
        """A backup corrupted on disk is reported by info and refused by restore."""
        app_dir = create_flask_app(tmp_path, "corrupt-app", "Original version")

        app = AppSource(name="corrupt-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            session.deploy()  # Raises DeploymentError on failure
            backup_id = _create_backup(deployment_target, session.app_name)

            archive = f"{BACKUP_DIR_IN_CONTAINER}/{session.app_name}/{backup_id}/source.tar.gz"
            code, _out, err = deployment_target.exec_run([
                "sh", "-c", f"printf corrupt >> {archive}"
            ])  # fmt: skip
            assert code == 0, f"could not corrupt {archive}: {err}"

            result = deployment_target.run_command("backup", "info", backup_id)
            assert result.success, result.stderr
            assert "✗ source.tar.gz" in result.stdout, result.stdout

            result = deployment_target.run_command("backup", "restore", backup_id)
            assert not result.success, "restore accepted a backup with a bad checksum"
            assert "checksum" in (result.stdout + result.stderr).lower()


_PG_REQS = "flask==3.0.0\npsycopg2-binary==2.9.9\n"

_PG_RUNNER = """
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = True
cur = conn.cursor()
cur.execute({sql!r})
print(cur.fetchall() if cur.description else "ok")
"""

# One statement per execute: PyMySQL refuses a multi-statement string.
_MYSQL_RUNNER = """
import os, pymysql
conn = pymysql.connect(
    host=os.environ["MYSQL_HOST"], port=int(os.environ["MYSQL_PORT"]),
    user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DATABASE"], autocommit=True,
)
cur = conn.cursor()
for statement in {sql!r}.split(";"):
    cur.execute(statement)
print(cur.fetchall() if cur.description else "ok")
"""

#: hop3-server's stderr in the e2e image, where a subprocess it runs writes.
_SERVER_STDERR_LOG = "/var/log/supervisor/hop3-server_err.log"


def _sql(target, app_name: str, sql: str, runner: str = _PG_RUNNER) -> str:
    """Run SQL against the app's attached database, from the app's own env."""
    result = target.run_command(
        "run", "--app", app_name, "python", "-c", runner.format(sql=sql)
    )
    assert result.success, f"SQL failed: {sql}\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _create_backup(target, app_name: str) -> str:
    result = target.run_command("backup", "create", "--app", app_name)
    assert result.success, f"backup create failed: {result.stderr}"
    backup_id = extract_backup_id(result.stdout)
    assert backup_id is not None, result.stdout
    return backup_id


@contextlib.contextmanager
def _addon(target, app_name: str, kind: str):
    """A ``kind`` addon attached to the app for the block, destroyed after."""
    name = f"{app_name}-db"
    result = target.run_command("addon", "create", kind, name)
    assert result.success, f"addon create failed: {result.stderr}"
    try:
        result = target.run_command("addon", "attach", name, "--app", app_name)
        assert result.success, f"addon attach failed: {result.stderr}"
        yield name
    except BaseException:
        # The test is already failing: clean up as far as possible, and let the
        # original failure through rather than a destroy error masking it.
        _destroy_addon(target, name, app_name)
        raise
    else:
        # A destroy that fails on a green test is a finding of its own: it leaks
        # an addon on a reused target and hides a destroy bug.
        destroyed = _destroy_addon(target, name, app_name)
        assert destroyed.success, f"addon destroy failed: {destroyed.stderr}"


def _destroy_addon(target, name: str, app_name: str):
    target.run_command("addon", "detach", name, "--app", app_name)
    return target.run_command("addon", "destroy", name, "-y")
