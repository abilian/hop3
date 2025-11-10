# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for backup commands."""

from __future__ import annotations

import json
import shutil
import tarfile

import pytest
from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hop3 import config as c
from hop3.commands.backup import (
    BackupCreateCmd,
    BackupDeleteCmd,
    BackupInfoCmd,
    BackupListCmd,
    BackupRestoreCmd,
)
from hop3.orm import App, EnvVar


@pytest.fixture
def test_db():
    """Create a test database.

    Uses in-memory SQLite database to support parallel test execution.
    Each test worker gets its own isolated in-memory database.
    """
    engine = create_engine("sqlite:///:memory:")
    BigIntAuditBase.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def test_app(test_db, tmp_path):
    """Create a test application."""
    # Override HOP3_ROOT for testing
    c.HOP3_ROOT = tmp_path
    c.APP_ROOT = tmp_path / "apps"
    c.BACKUP_ROOT = tmp_path / "backups"

    # Create root directories
    c.APP_ROOT.mkdir(parents=True, exist_ok=True)
    c.BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

    # Create app
    app = App(name="test-app", hostname="test.example.com", port=8000)
    test_db.add(app)
    test_db.commit()

    # Create app directories and files
    app.create()

    # Add some source code
    repo_path = app.repo_path
    (repo_path / "README.md").write_text("# Test App")

    # Add some data
    data_path = app.data_path
    (data_path / "data.txt").write_text("Important data")

    # Add environment variables
    env_vars = [
        EnvVar(name="FOO", value="bar", app=app),
        EnvVar(name="DEBUG", value="true", app=app),
        EnvVar(name="SECRET", value="s3cr3t", app=app),
    ]
    for env_var in env_vars:
        test_db.add(env_var)
    test_db.commit()

    yield app

    # Cleanup
    if app.app_path.exists():
        shutil.rmtree(app.app_path)


class TestBackupCreateCommand:
    """Test backup:create command."""

    def test_create_backup_simple(self, test_db, test_app):
        """Test creating a simple backup without services."""
        cmd = BackupCreateCmd(db_session=test_db)

        result = cmd.call("test-app", "--no-services")

        # Should return success messages
        assert len(result) >= 2
        assert result[1]["t"] == "success"

        # Check that backup was created
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        assert backup_dir.exists()

        # Should have one backup directory
        backup_dirs = list(backup_dir.iterdir())
        assert len(backup_dirs) == 1

        # Check backup contents
        backup_path = backup_dirs[0]
        assert (backup_path / "metadata.json").exists()
        assert (backup_path / "source.tar.gz").exists()
        assert (backup_path / "data.tar.gz").exists()
        assert (backup_path / "env.json").exists()

    def test_create_backup_includes_env_vars(self, test_db, test_app):
        """Test that backup includes environment variables."""
        cmd = BackupCreateCmd(db_session=test_db)

        result = cmd.call("test-app", "--no-services")

        # Find the backup directory
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        backup_path = next(iter(backup_dir.iterdir()))

        # Check env.json
        env_file = backup_path / "env.json"
        assert env_file.exists()

        with open(env_file) as f:
            env_data = json.load(f)

        assert env_data["FOO"] == "bar"
        assert env_data["DEBUG"] == "true"
        assert env_data["SECRET"] == "s3cr3t"

    def test_create_backup_includes_source(self, test_db, test_app):
        """Test that backup includes source code."""
        cmd = BackupCreateCmd(db_session=test_db)

        result = cmd.call("test-app", "--no-services")

        # Find the backup directory
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        backup_path = next(iter(backup_dir.iterdir()))

        # Check source.tar.gz
        source_tar = backup_path / "source.tar.gz"
        assert source_tar.exists()

        # Extract and verify
        with tarfile.open(source_tar, "r:gz") as tar:
            members = tar.getnames()
            assert "git/README.md" in members

    def test_create_backup_includes_data(self, test_db, test_app):
        """Test that backup includes application data."""
        cmd = BackupCreateCmd(db_session=test_db)

        result = cmd.call("test-app", "--no-services")

        # Find the backup directory
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        backup_path = next(iter(backup_dir.iterdir()))

        # Check data.tar.gz
        data_tar = backup_path / "data.tar.gz"
        assert data_tar.exists()

        # Extract and verify
        with tarfile.open(data_tar, "r:gz") as tar:
            members = tar.getnames()
            assert "data/data.txt" in members

    def test_create_backup_generates_metadata(self, test_db, test_app):
        """Test that backup generates correct metadata."""
        cmd = BackupCreateCmd(db_session=test_db)

        result = cmd.call("test-app", "--no-services")

        # Find the backup directory
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        backup_path = next(iter(backup_dir.iterdir()))

        # Check metadata.json
        metadata_file = backup_path / "metadata.json"
        assert metadata_file.exists()

        with open(metadata_file) as f:
            metadata = json.load(f)

        assert metadata["app_name"] == "test-app"
        assert metadata["format_version"] == "1.0"
        assert metadata["env_vars_count"] == 3
        assert "checksums" in metadata
        assert "source.tar.gz" in metadata["checksums"]
        assert "data.tar.gz" in metadata["checksums"]
        assert "env.json" in metadata["checksums"]

    def test_create_backup_nonexistent_app(self, test_db):
        """Test creating backup for non-existent app."""
        cmd = BackupCreateCmd(db_session=test_db)

        result = cmd.call("nonexistent-app")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]

    def test_create_backup_no_args(self, test_db):
        """Test backup:create with no arguments."""
        cmd = BackupCreateCmd(db_session=test_db)

        result = cmd.call()

        assert len(result) == 1
        assert result[0]["t"] == "text"
        assert "Usage" in result[0]["text"]


class TestBackupListCommand:
    """Test backup:list command."""

    def test_list_empty(self, test_db):
        """Test listing when no backups exist."""
        cmd = BackupListCmd(db_session=test_db)

        result = cmd.call()

        assert len(result) == 1
        assert result[0]["t"] == "text"
        assert "No backups found" in result[0]["text"]

    def test_list_backups(self, test_db, test_app):
        """Test listing backups."""
        # Create a backup first
        create_cmd = BackupCreateCmd(db_session=test_db)
        create_cmd.call("test-app", "--no-services")

        # List backups
        list_cmd = BackupListCmd(db_session=test_db)
        result = list_cmd.call()

        assert len(result) == 1
        assert result[0]["t"] == "table"
        assert len(result[0]["rows"]) == 1

        # Check row data
        row = result[0]["rows"][0]
        assert row[1] == "test-app"  # App name

    def test_list_filter_by_app(self, test_db, test_app):
        """Test filtering backups by app."""
        # Create a backup
        create_cmd = BackupCreateCmd(db_session=test_db)
        create_cmd.call("test-app", "--no-services")

        # List backups for this app
        list_cmd = BackupListCmd(db_session=test_db)
        result = list_cmd.call("test-app")

        assert len(result) == 1
        assert result[0]["t"] == "table"
        assert len(result[0]["rows"]) == 1

    def test_list_filter_by_nonexistent_app(self, test_db, test_app):
        """Test filtering by non-existent app."""
        # Create a backup
        create_cmd = BackupCreateCmd(db_session=test_db)
        create_cmd.call("test-app", "--no-services")

        # List backups for different app
        list_cmd = BackupListCmd(db_session=test_db)
        result = list_cmd.call("other-app")

        assert len(result) == 1
        assert "No backups found" in result[0]["text"]


class TestBackupInfoCommand:
    """Test backup:info command."""

    def test_info_backup(self, test_db, test_app):
        """Test getting backup info."""
        # Create a backup
        create_cmd = BackupCreateCmd(db_session=test_db)
        create_result = create_cmd.call("test-app", "--no-services")

        # Extract backup ID from result
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        backup_id = next(iter(backup_dir.iterdir())).name

        # Get backup info
        info_cmd = BackupInfoCmd(db_session=test_db)
        result = info_cmd.call(backup_id)

        assert len(result) == 1
        assert result[0]["t"] == "text"
        text = result[0]["text"]

        assert "Backup Information" in text
        assert backup_id in text
        assert "test-app" in text
        assert "Environment: 3 variables" in text

    def test_info_nonexistent_backup(self, test_db):
        """Test getting info for non-existent backup."""
        info_cmd = BackupInfoCmd(db_session=test_db)
        result = info_cmd.call("nonexistent_backup")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]

    def test_info_no_args(self, test_db):
        """Test backup:info with no arguments."""
        info_cmd = BackupInfoCmd(db_session=test_db)
        result = info_cmd.call()

        assert len(result) == 1
        assert result[0]["t"] == "text"
        assert "Usage" in result[0]["text"]


class TestBackupRestoreCommand:
    """Test backup:restore command."""

    def test_restore_backup(self, test_db, test_app):
        """Test restoring a backup."""
        # Create a backup
        create_cmd = BackupCreateCmd(db_session=test_db)
        create_cmd.call("test-app", "--no-services")

        # Get backup ID
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        backup_id = next(iter(backup_dir.iterdir())).name

        # Modify app data
        (test_app.data_path / "data.txt").write_text("Modified data")

        # Restore backup
        restore_cmd = BackupRestoreCmd(db_session=test_db)
        result = restore_cmd.call(backup_id)

        assert len(result) >= 2
        assert result[1]["t"] == "success"

        # Check that data was restored
        data_content = (test_app.data_path / "data.txt").read_text()
        assert data_content == "Important data"

    def test_restore_to_different_app(self, test_db, test_app, tmp_path):
        """Test restoring backup to different app name."""
        # Create a backup
        create_cmd = BackupCreateCmd(db_session=test_db)
        create_cmd.call("test-app", "--no-services")

        # Get backup ID
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        backup_id = next(iter(backup_dir.iterdir())).name

        # Restore to different app
        restore_cmd = BackupRestoreCmd(db_session=test_db)
        result = restore_cmd.call(backup_id, "--target-app", "restored-app")

        assert len(result) >= 2
        assert result[1]["t"] == "success"

        # Check that new app was created
        restored_app_path = c.APP_ROOT / "restored-app"
        assert restored_app_path.exists()
        assert (restored_app_path / "data" / "data.txt").exists()

    def test_restore_restores_env_vars(self, test_db, test_app):
        """Test that restore includes environment variables."""
        # Create a backup
        create_cmd = BackupCreateCmd(db_session=test_db)
        create_cmd.call("test-app", "--no-services")

        # Get backup ID
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        backup_id = next(iter(backup_dir.iterdir())).name

        # Clear env vars
        test_app.env_vars.clear()
        test_db.commit()

        # Restore backup
        restore_cmd = BackupRestoreCmd(db_session=test_db)
        restore_cmd.call(backup_id)

        # Refresh app
        test_db.refresh(test_app)

        # Check env vars were restored
        assert len(test_app.env_vars) == 3
        env_dict = {ev.name: ev.value for ev in test_app.env_vars}
        assert env_dict["FOO"] == "bar"
        assert env_dict["DEBUG"] == "true"

    def test_restore_nonexistent_backup(self, test_db):
        """Test restoring non-existent backup."""
        restore_cmd = BackupRestoreCmd(db_session=test_db)
        result = restore_cmd.call("nonexistent_backup")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]

    def test_restore_no_args(self, test_db):
        """Test backup:restore with no arguments."""
        restore_cmd = BackupRestoreCmd(db_session=test_db)
        result = restore_cmd.call()

        assert len(result) == 1
        assert result[0]["t"] == "text"
        assert "Usage" in result[0]["text"]


class TestBackupDeleteCommand:
    """Test backup:delete command."""

    def test_delete_backup(self, test_db, test_app):
        """Test deleting a backup."""
        # Create a backup
        create_cmd = BackupCreateCmd(db_session=test_db)
        create_cmd.call("test-app", "--no-services")

        # Get backup ID
        backup_dir = c.BACKUP_ROOT / "apps" / "test-app"
        backup_path = next(iter(backup_dir.iterdir()))
        backup_id = backup_path.name

        # Delete backup
        delete_cmd = BackupDeleteCmd(db_session=test_db)
        result = delete_cmd.call(backup_id)

        assert len(result) >= 2
        assert result[1]["t"] == "success"

        # Check that backup was deleted
        assert not backup_path.exists()

    def test_delete_nonexistent_backup(self, test_db):
        """Test deleting non-existent backup."""
        delete_cmd = BackupDeleteCmd(db_session=test_db)
        result = delete_cmd.call("nonexistent_backup")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]

    def test_delete_no_args(self, test_db):
        """Test backup:delete with no arguments."""
        delete_cmd = BackupDeleteCmd(db_session=test_db)
        result = delete_cmd.call()

        assert len(result) == 1
        assert result[0]["t"] == "text"
        assert "Usage" in result[0]["text"]
