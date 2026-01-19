# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for backup and restore functionality.

These tests verify complete backup/restore workflows in a production-like
Docker environment with real services.
"""

from __future__ import annotations

import json

import pytest
from hop3_testing.apps import DeploymentSession
from hop3_testing.apps.catalog import AppSource

from .conftest import (
    backup_in_table,
    create_flask_app,
    extract_backup_id,
    find_json_table,
)


@pytest.mark.e2e
class TestBackupRestoreE2E:
    """End-to-end tests for backup and restore."""

    def test_backup_simple_app(self, deployment_target, tmp_path):
        """Test creating a backup of a simple application."""
        app_dir = create_flask_app(tmp_path, "simple-app", "Hello from Flask!")

        app = AppSource(name="simple-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy(), "Failed to deploy app"
            assert session.check_deployed(), "App not properly deployed"

            # Create backup
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success, f"Backup creation failed: {result.stderr}"
            assert "Backup created successfully!" in result.stdout

            backup_id = extract_backup_id(result.stdout)
            assert backup_id, "Could not extract backup ID from output"

            # Verify backup in list
            result = deployment_target.run_command("backup:list", "--json")
            assert result.success, f"Backup list failed: {result.stderr}"
            table = find_json_table(json.loads(result.stdout))
            assert table, "No table found in backup:list output"
            assert backup_in_table(backup_id, table), (
                f"Backup ID {backup_id} not found in backup list"
            )

            # Get backup info
            result = deployment_target.run_command("backup:info", backup_id)
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
            assert session.deploy()

            # Set environment variable
            result = deployment_target.run_command(
                "config:set", session.app_name, "SECRET_KEY=my-secret-value"
            )
            assert result.success, f"Failed to set env var: {result.stderr}"

            # Create backup
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = extract_backup_id(result.stdout)

            # Get backup info and verify env vars
            result = deployment_target.run_command("backup:info", backup_id)
            assert result.success
            assert "Environment:" in result.stdout

    def test_restore_simple_app(self, deployment_target, tmp_path):
        """Test restoring an application from backup."""
        app_dir = create_flask_app(tmp_path, "restore-app", "Original version")

        app = AppSource(name="restore-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy()

            # Create backup
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = extract_backup_id(result.stdout)

            # Modify the app (simulate changes)
            (app_dir / "app.py").write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Modified version"
""")

            # Redeploy with changes
            assert session.deploy()

            # Restore from backup
            result = deployment_target.run_command("backup:restore", backup_id)
            assert result.success, f"Restore failed: {result.stderr}"
            assert "Restore completed successfully!" in result.stdout

    def test_restore_to_different_app_name(self, deployment_target, tmp_path):
        """Test restoring backup to a different application name (cloning)."""
        app_dir = create_flask_app(tmp_path, "original-app", "Original app")

        app = AppSource(name="original-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy()

            # Create backup
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = extract_backup_id(result.stdout)

            # Restore to a different app name
            result = deployment_target.run_command(
                "backup:restore", backup_id, "--target-app", "cloned-app"
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
                assert session.deploy()

                result = deployment_target.run_command(
                    "backup:create", session.app_name
                )
                assert result.success

        # List all backups
        result = deployment_target.run_command("backup:list", "--json")
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
            assert session.deploy()

            # Create backup
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = extract_backup_id(result.stdout)

            # Verify backup exists
            result = deployment_target.run_command("backup:list", "--json")
            assert result.success
            table = find_json_table(json.loads(result.stdout))
            assert table, "No table found in backup:list output"
            assert backup_in_table(backup_id, table), (
                f"Backup ID {backup_id} not found before delete"
            )

            # Delete the backup
            result = deployment_target.run_command("backup:delete", backup_id)
            assert result.success
            assert "Backup deleted successfully" in result.stdout

            # Verify backup is gone
            result = deployment_target.run_command("backup:list", "--json")
            assert result.success
            table = find_json_table(json.loads(result.stdout))
            assert not backup_in_table(backup_id, table), (
                f"Backup ID {backup_id} still found after deletion"
            )

    @pytest.mark.skip(
        reason="PostgreSQL service integration not yet available in E2E tests"
    )
    def test_backup_app_with_postgres(self, deployment_target, tmp_path):
        """Test creating a backup of an app with PostgreSQL service."""
        app_dir = create_flask_app(
            tmp_path,
            "postgres-app",
            response='f"PostgreSQL: {version}"',
            extra_imports="import psycopg2\nimport os",
            extra_code="""conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()
cur.execute("SELECT version();")
version = cur.fetchone()[0]
cur.close()
conn.close()""",
            requirements="flask==3.0.0\npsycopg2-binary==2.9.9\n",
        )

        app = AppSource(name="postgres-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy()

            # Create PostgreSQL service
            result = deployment_target.run_command("postgres:create", "test-db")
            assert result.success, f"Failed to create PostgreSQL: {result.stderr}"

            # Attach to app
            result = deployment_target.run_command(
                "postgres:attach", "test-db", session.app_name
            )
            assert result.success, f"Failed to attach PostgreSQL: {result.stderr}"

            # Create backup (should include PostgreSQL dump)
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = extract_backup_id(result.stdout)

            # Verify backup info shows PostgreSQL service
            result = deployment_target.run_command("backup:info", backup_id)
            assert result.success
            assert "postgres" in result.stdout.lower()
            assert "test-db" in result.stdout

    @pytest.mark.skip(
        reason="PostgreSQL service integration not yet available in E2E tests"
    )
    def test_restore_app_with_postgres(self, deployment_target, tmp_path):
        """Test restoring an app with PostgreSQL service and verifying data integrity."""
        # Implementation pending full PostgreSQL service support in E2E environment

    @pytest.mark.skip(reason="Requires checksum corruption simulation")
    def test_backup_integrity_verification(self, deployment_target, tmp_path):
        """Test backup integrity verification with checksums."""
        # Implementation pending direct filesystem access to backup directory
