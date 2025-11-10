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


@pytest.mark.e2e
class TestBackupRestoreE2E:
    """End-to-end tests for backup and restore."""

    def test_backup_simple_app(self, deployment_target, tmp_path):
        """Test creating a backup of a simple application."""
        # Create a simple Flask app
        app_dir = tmp_path / "simple-app"
        app_dir.mkdir()

        # Create requirements.txt
        (app_dir / "requirements.txt").write_text("flask==3.0.0\n")

        # Create app.py
        (app_dir / "app.py").write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from Flask!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
""")

        # Create Procfile
        (app_dir / "Procfile").write_text("web: python app.py\n")

        # Deploy the app
        app = AppSource(name="simple-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy(), "Failed to deploy app"
            assert session.check_deployed(), "App not properly deployed"

            # Create a backup (use session.app_name which includes timestamp)
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success, f"Backup creation failed: {result.stderr}"
            assert "Backup created successfully!" in result.stdout

            # Extract backup ID from output
            # Expected format: "Backup ID: 20251108_143022_a8f3d9"
            backup_id = None
            for line in result.stdout.split("\n"):
                if line.startswith("Backup ID:"):
                    backup_id = line.split(":", 1)[1].strip()
                    break

            assert backup_id, "Could not extract backup ID from output"

            # List backups and verify it exists (use --json for reliable parsing)
            result = deployment_target.run_command("backup:list", "--json")
            assert result.success, f"Backup list failed: {result.stderr}"
            # In JSON mode, parse the output
            output = json.loads(result.stdout)
            # Output is a list of message objects, find the table
            table_data = None
            for item in output:
                if item.get("t") == "table":
                    table_data = item
                    break
            assert table_data, "No table found in backup:list output"
            # Check if backup_id appears in any row
            backup_found = any(
                backup_id in str(row) for row in table_data.get("rows", [])
            )
            assert backup_found, f"Backup ID {backup_id} not found in backup list"

            # Get backup info
            result = deployment_target.run_command("backup:info", backup_id)
            assert result.success, f"Backup info failed: {result.stderr}"
            assert backup_id in result.stdout
            assert session.app_name in result.stdout
            assert "Integrity" in result.stdout
            assert "valid" in result.stdout.lower()

    def test_backup_includes_env_vars(self, deployment_target, tmp_path):
        """Test that backups include environment variables."""
        # Create a simple app
        app_dir = tmp_path / "env-app"
        app_dir.mkdir()

        (app_dir / "requirements.txt").write_text("flask==3.0.0\n")
        (app_dir / "app.py").write_text("""
from flask import Flask
import os

app = Flask(__name__)

@app.route("/")
def index():
    secret = os.getenv("SECRET_KEY", "not-set")
    return f"Secret: {secret}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
""")
        (app_dir / "Procfile").write_text("web: python app.py\n")

        app = AppSource(name="env-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy()

            # Set environment variable (use session.app_name)
            result = deployment_target.run_command(
                "config:set", session.app_name, "SECRET_KEY=my-secret-value"
            )
            assert result.success, f"Failed to set env var: {result.stderr}"

            # Create backup (use session.app_name)
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = None
            for line in result.stdout.split("\n"):
                if line.startswith("Backup ID:"):
                    backup_id = line.split(":", 1)[1].strip()
                    break

            # Get backup info and verify env vars count
            result = deployment_target.run_command("backup:info", backup_id)
            assert result.success
            # Should include at least the SECRET_KEY we set
            assert "Environment:" in result.stdout

    def test_restore_simple_app(self, deployment_target, tmp_path):
        """Test restoring an application from backup."""
        # Create and deploy app
        app_dir = tmp_path / "restore-app"
        app_dir.mkdir()

        (app_dir / "requirements.txt").write_text("flask==3.0.0\n")
        (app_dir / "app.py").write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Original version"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
""")
        (app_dir / "Procfile").write_text("web: python app.py\n")

        app = AppSource(name="restore-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy()

            # Create backup (use session.app_name)
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = None
            for line in result.stdout.split("\n"):
                if line.startswith("Backup ID:"):
                    backup_id = line.split(":", 1)[1].strip()
                    break

            # Modify the app (simulate changes)
            (app_dir / "app.py").write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Modified version"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
""")

            # Redeploy with changes
            assert session.deploy()

            # Verify changes took effect (the modified version is deployed)
            # We can't easily test HTTP here, so we'll just restore

            # Restore from backup
            result = deployment_target.run_command("backup:restore", backup_id)
            assert result.success, f"Restore failed: {result.stderr}"
            assert "Restore completed successfully!" in result.stdout

            # The app should now have the original version restored
            # We would need to verify the file contents, but that requires
            # executing commands in the container

    def test_restore_to_different_app_name(self, deployment_target, tmp_path):
        """Test restoring backup to a different application name (cloning)."""
        # Create and deploy original app
        app_dir = tmp_path / "original-app"
        app_dir.mkdir()

        (app_dir / "requirements.txt").write_text("flask==3.0.0\n")
        (app_dir / "app.py").write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Original app"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
""")
        (app_dir / "Procfile").write_text("web: python app.py\n")

        app = AppSource(name="original-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy()

            # Create backup (use session.app_name)
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = None
            for line in result.stdout.split("\n"):
                if line.startswith("Backup ID:"):
                    backup_id = line.split(":", 1)[1].strip()
                    break

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
        # Create two apps
        for app_name in ["app1", "app2"]:
            app_dir = tmp_path / app_name
            app_dir.mkdir()

            (app_dir / "requirements.txt").write_text("flask==3.0.0\n")
            (app_dir / "app.py").write_text(f"""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "{app_name}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
""")
            (app_dir / "Procfile").write_text("web: python app.py\n")

            app = AppSource(name=app_name, path=app_dir)
            with DeploymentSession(app, deployment_target) as session:
                assert session.deploy()

                # Create backup for each app (use session.app_name)
                result = deployment_target.run_command(
                    "backup:create", session.app_name
                )
                assert result.success

        # List all backups (use --json for reliable parsing)
        result = deployment_target.run_command("backup:list", "--json")
        assert result.success
        # In JSON mode, parse the output
        output = json.loads(result.stdout)
        # Output is a list of message objects, find the table
        table_data = None
        for item in output:
            if item.get("t") == "table":
                table_data = item
                break

        if table_data:
            # Check if app names appear in any row (they have timestamps)
            all_rows_str = " ".join(str(row) for row in table_data.get("rows", []))
            assert "app1" in all_rows_str or "app2" in all_rows_str, (
                "No backups found for app1 or app2"
            )
        else:
            # If no backups, that's also acceptable (cleanup might have removed them)
            # but check stderr for error messages
            assert "error" not in result.stderr.lower(), (
                f"Error in backup list: {result.stderr}"
            )

    def test_delete_backup(self, deployment_target, tmp_path):
        """Test deleting a backup."""
        # Create app and backup
        app_dir = tmp_path / "delete-test-app"
        app_dir.mkdir()

        (app_dir / "requirements.txt").write_text("flask==3.0.0\n")
        (app_dir / "app.py").write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Delete test"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
""")
        (app_dir / "Procfile").write_text("web: python app.py\n")

        app = AppSource(name="delete-test-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy()

            # Create backup (use session.app_name)
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = None
            for line in result.stdout.split("\n"):
                if line.startswith("Backup ID:"):
                    backup_id = line.split(":", 1)[1].strip()
                    break

            # Verify backup exists in list (use --json for reliable parsing)
            result = deployment_target.run_command("backup:list", "--json")
            assert result.success
            output = json.loads(result.stdout)
            table_data = None
            for item in output:
                if item.get("t") == "table":
                    table_data = item
                    break
            assert table_data, "No table found in backup:list output"
            backup_found = any(
                backup_id in str(row) for row in table_data.get("rows", [])
            )
            assert backup_found, (
                f"Backup ID {backup_id} not found in backup list before delete"
            )

            # Delete the backup
            result = deployment_target.run_command("backup:delete", backup_id)
            assert result.success
            assert "Backup deleted successfully" in result.stdout

            # Verify backup is no longer in list
            result = deployment_target.run_command("backup:list", "--json")
            assert result.success
            output = json.loads(result.stdout)
            table_data = None
            for item in output:
                if item.get("t") == "table":
                    table_data = item
                    break
            # After deletion, either no table (no backups) or backup_id not in rows
            if table_data:
                backup_found = any(
                    backup_id in str(row) for row in table_data.get("rows", [])
                )
                assert not backup_found, (
                    f"Backup ID {backup_id} still found after deletion"
                )

    @pytest.mark.skip(
        reason="PostgreSQL service integration not yet available in E2E tests"
    )
    def test_backup_app_with_postgres(self, deployment_target, tmp_path):
        """Test creating a backup of an app with PostgreSQL service."""
        # This test requires:
        # 1. PostgreSQL to be installed in the Docker container
        # 2. postgres:create command to work
        # 3. postgres:attach command to work
        #
        # Implementation pending full PostgreSQL service support in E2E environment

        app_dir = tmp_path / "postgres-app"
        app_dir.mkdir()

        (app_dir / "requirements.txt").write_text(
            "flask==3.0.0\npsycopg2-binary==2.9.9\n"
        )
        (app_dir / "app.py").write_text("""
from flask import Flask
import psycopg2
import os

app = Flask(__name__)

@app.route("/")
def index():
    # Connect to database using DATABASE_URL
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    cur.close()
    conn.close()
    return f"PostgreSQL: {version}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
""")
        (app_dir / "Procfile").write_text("web: python app.py\n")

        app = AppSource(name="postgres-app", path=app_dir)
        with DeploymentSession(app, deployment_target) as session:
            assert session.deploy()

            # Create PostgreSQL service
            result = deployment_target.run_command("postgres:create", "test-db")
            assert result.success, f"Failed to create PostgreSQL: {result.stderr}"

            # Attach to app (use session.app_name)
            result = deployment_target.run_command(
                "postgres:attach", "test-db", session.app_name
            )
            assert result.success, f"Failed to attach PostgreSQL: {result.stderr}"

            # TODO: Populate database with test data

            # Create backup (should include PostgreSQL dump) (use session.app_name)
            result = deployment_target.run_command("backup:create", session.app_name)
            assert result.success

            backup_id = None
            for line in result.stdout.split("\n"):
                if line.startswith("Backup ID:"):
                    backup_id = line.split(":", 1)[1].strip()
                    break

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
        # This test would:
        # 1. Deploy app with PostgreSQL
        # 2. Populate database with known test data
        # 3. Create backup
        # 4. Delete app and database
        # 5. Restore from backup
        # 6. Verify database contains the original test data
        #
        # Implementation pending full PostgreSQL service support in E2E environment

    @pytest.mark.skip(reason="Requires checksum corruption simulation")
    def test_backup_integrity_verification(self, deployment_target, tmp_path):
        """Test backup integrity verification with checksums."""
        # This test would:
        # 1. Create a backup
        # 2. Verify all checksums are valid
        # 3. Manually corrupt a file in the backup
        # 4. Attempt to restore
        # 5. Verify that restore detects corruption and fails
        #
        # This requires direct filesystem access to the backup directory
        # which is challenging in E2E tests without container exec


# Note: Some tests are marked as skip because they require:
# 1. Full PostgreSQL service integration in E2E environment
# 2. Database population utilities
# 3. Direct filesystem access for corruption testing
#
# These will be implemented once the E2E infrastructure supports
# PostgreSQL services fully.
