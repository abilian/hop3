# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""State-based integration tests for backup functionality.

These tests verify the BackupManager with real database state changes
and mock only external I/O boundaries (file system operations for
tar/backup files, subprocess if used).
"""

from __future__ import annotations

import json
import shutil
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

from hop3.config import HopConfig
from hop3.core.backup import BackupManager, BackupManifest
from hop3.orm import App, Backup, BackupStateEnum, EnvVar
from hop3.orm.session import BigIntAuditBase


@pytest.fixture
def backup_db_engine():
    """Create fresh in-memory test database for backup tests.

    Uses isolated in-memory SQLite to support parallel execution.

    Yields:
        SQLAlchemy engine bound to in-memory database
    """
    database_uri = "sqlite:///:memory:"
    engine = create_engine(database_uri, echo=False)

    # Create all tables
    with engine.begin() as conn:
        BigIntAuditBase.metadata.create_all(conn)

    yield engine

    # Cleanup
    engine.dispose()


@pytest.fixture
def backup_db_session(backup_db_engine):
    """Create database session for backup tests.

    Provides fresh session for querying test state.

    Args:
        backup_db_engine: Fresh in-memory database engine

    Yields:
        SQLAlchemy Session for database operations
    """
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=backup_db_engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def backup_test_config(tmp_path):
    """Configure Hop3 with test directories.

    Sets up test backup and app root directories.

    Args:
        tmp_path: pytest temporary directory fixture

    Returns:
        Configured HopConfig instance
    """
    HopConfig.reset_instance()
    test_config = HopConfig(hop3_root=tmp_path)
    HopConfig.set_instance(test_config)

    # Create root directories
    test_config.APP_ROOT.mkdir(parents=True, exist_ok=True)
    test_config.BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

    yield test_config

    # Cleanup
    HopConfig.reset_instance()


@pytest.fixture
def sample_app(backup_db_session, backup_test_config):
    """Create test application with files and environment variables.

    ARRANGE: Sets up complete app state with repo, data, and env vars.

    Args:
        backup_db_session: Database session for persistence
        backup_test_config: Hop3 configuration with test directories

    Yields:
        App instance with populated state
    """
    # Create app in database
    app = App(name="test-app", hostname="test.example.com", port=8000)
    backup_db_session.add(app)
    backup_db_session.commit()

    # Create app directories and files
    app.create()

    # Add source code
    repo_path = app.repo_path
    (repo_path / "README.md").write_text("# Test App")
    (repo_path / ".git" / "config").parent.mkdir(parents=True, exist_ok=True)
    (repo_path / ".git" / "config").write_text("# Git config")

    # Add data
    data_path = app.data_path
    (data_path / "data.txt").write_text("Important data")

    # Add environment variables
    env_vars = [
        EnvVar(name="FOO", value="bar", app=app),
        EnvVar(name="DEBUG", value="true", app=app),
        EnvVar(name="SECRET", value="s3cr3t", app=app),
    ]
    for env_var in env_vars:
        backup_db_session.add(env_var)
    backup_db_session.commit()

    yield app

    # Cleanup
    if app.app_path.exists():
        shutil.rmtree(app.app_path)


@pytest.mark.integration
class TestBackupManifestIntegration:
    """Integration tests for BackupManifest dataclass with real state."""

    def test_create_manifest_persists_all_fields(self, backup_db_session):
        """Test creating a manifest captures all required fields.

        ARRANGE: Create manifest with complete data
        ACT: Verify all fields are present
        ASSERT: Check field values match input

        Tests that BackupManifest correctly stores all backup metadata.
        """
        manifest = BackupManifest(
            backup_id="20251030_143022_a8f3d9",
            app_name="test-app",
            created_at="2025-10-30T14:30:22Z",
            format_version="1.0",
            hop3_version="0.8.0",
            size_bytes=15728640,
            checksums={"source.tar.gz": "sha256:abc123"},
            app_metadata={"hostname": "test.example.com", "port": 8000},
            addons=[
                {
                    "type": "postgres",
                    "name": "test-db",
                    "backup_file": "addons/postgres_test-db.sql",
                    "size_bytes": 1024,
                }
            ],
            env_vars_count=12,
            expires_after=0,
        )

        assert manifest.backup_id == "20251030_143022_a8f3d9"
        assert manifest.app_name == "test-app"
        assert manifest.size_bytes == 15728640
        assert len(manifest.addons) == 1
        assert manifest.addons[0]["type"] == "postgres"

    def test_manifest_serialization_roundtrip(self, tmp_path):
        """Test JSON serialization roundtrip persists manifest state.

        ARRANGE: Create manifest and write to file
        ACT: Read back from file
        ASSERT: Verify all fields match original

        Tests that manifest can be persisted to disk and restored
        without data loss.
        """
        original = BackupManifest(
            backup_id="test_backup",
            app_name="test-app",
            created_at="2025-10-30T14:30:22Z",
            format_version="1.0",
            hop3_version="0.8.0",
            size_bytes=1024,
            checksums={"file.tar.gz": "sha256:123"},
            app_metadata={"port": 8000},
            addons=[{"type": "postgres", "name": "db"}],
            env_vars_count=5,
            expires_after=7,
        )

        manifest_file = tmp_path / "metadata.json"
        original.to_file(manifest_file)

        assert manifest_file.exists()
        with open(manifest_file) as f:
            data = json.load(f)
            assert data["backup_id"] == "test_backup"

        restored = BackupManifest.from_file(manifest_file)

        assert restored.backup_id == original.backup_id
        assert restored.app_name == original.app_name
        assert restored.size_bytes == original.size_bytes
        assert restored.checksums == original.checksums
        assert restored.addons == original.addons


@pytest.mark.integration
class TestBackupManagerBasicOperations:
    """Integration tests for BackupManager basic operations with real database."""

    def test_manager_initialization_stores_session(self, backup_db_session):
        """Test BackupManager initializes with database session.

        ARRANGE: Create manager with session
        ACT: Access session
        ASSERT: Verify session is stored

        Tests that manager correctly stores database reference.
        """
        manager = BackupManager(backup_db_session)

        # ACT & ASSERT
        assert manager.db_session == backup_db_session

    def test_generate_backup_id_creates_valid_format(self, backup_db_session):
        """Test backup ID generation follows correct format.

        ARRANGE: Create manager and generate ID
        ACT: Parse generated ID
        ASSERT: Verify format is YYYYMMDD_HHMMSS_XXXXXX

        Tests that backup IDs are properly formatted for parsing.
        """
        manager = BackupManager(backup_db_session)

        backup_id = manager._generate_backup_id()

        parts = backup_id.split("_")
        assert len(parts) == 3, f"Expected 3 parts, got {len(parts)}"
        assert len(parts[0]) == 8, "Date should be YYYYMMDD (8 chars)"
        assert len(parts[1]) == 6, "Time should be HHMMSS (6 chars)"
        assert len(parts[2]) == 6, "Random suffix should be 6 hex chars"

    def test_generate_backup_ids_are_unique(self, backup_db_session):
        """Test that multiple backup IDs are unique.

        ARRANGE: Generate multiple IDs
        ACT: Add to set to check uniqueness
        ASSERT: All IDs should be different

        Tests that randomness ensures unique IDs even in rapid succession.
        """
        manager = BackupManager(backup_db_session)

        ids = {manager._generate_backup_id() for _ in range(10)}

        assert len(ids) == 10, "Not all backup IDs were unique"

    def test_calculate_checksum_produces_sha256_format(
        self, backup_db_session, tmp_path
    ):
        """Test checksum calculation produces valid SHA256 format.

        ARRANGE: Create test file with content
        ACT: Calculate checksum
        ASSERT: Verify SHA256 format and consistency

        Tests that checksums are properly formatted and deterministic.
        """
        manager = BackupManager(backup_db_session)
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        checksum = manager._calculate_checksum(test_file)

        assert checksum.startswith("sha256:")
        assert len(checksum) == 71  # "sha256:" (7) + 64 hex chars

    def test_calculate_checksum_is_deterministic(self, backup_db_session, tmp_path):
        """Test that same file content produces same checksum.

        ARRANGE: Create test file
        ACT: Calculate checksum twice
        ASSERT: Checksums should match

        Tests that checksum calculation is deterministic.
        """
        manager = BackupManager(backup_db_session)
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        checksum1 = manager._calculate_checksum(test_file)
        checksum2 = manager._calculate_checksum(test_file)

        assert checksum1 == checksum2

    def test_calculate_checksum_differs_for_different_content(
        self, backup_db_session, tmp_path
    ):
        """Test different file content produces different checksums.

        ARRANGE: Create two files with different content
        ACT: Calculate checksums for each
        ASSERT: Checksums should differ

        Tests checksum correctness for different content.
        """
        manager = BackupManager(backup_db_session)
        file1 = tmp_path / "test1.txt"
        file2 = tmp_path / "test2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")

        checksum1 = manager._calculate_checksum(file1)
        checksum2 = manager._calculate_checksum(file2)

        assert checksum1 != checksum2

    def test_verify_checksums_succeeds_for_valid_files(
        self, backup_db_session, tmp_path
    ):
        """Test checksum verification passes for valid backup files.

        ARRANGE: Create files and calculate their checksums
        ACT: Verify checksums
        ASSERT: Verification should pass

        Tests that verification correctly validates backup integrity.
        """
        manager = BackupManager(backup_db_session)
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")

        checksums = {
            "file1.txt": manager._calculate_checksum(file1),
            "file2.txt": manager._calculate_checksum(file2),
        }

        # ACT & ASSERT
        assert manager._verify_checksums(tmp_path, checksums) is True

    def test_verify_checksums_fails_on_corrupted_file(
        self, backup_db_session, tmp_path
    ):
        """Test checksum verification fails when file is modified.

        ARRANGE: Create file, calculate checksum, then modify it
        ACT: Verify checksums
        ASSERT: Verification should fail

        Tests that verification detects file corruption.
        """
        manager = BackupManager(backup_db_session)
        test_file = tmp_path / "test.txt"
        test_file.write_text("Original content")

        checksum = manager._calculate_checksum(test_file)

        test_file.write_text("Modified content")

        checksums = {"test.txt": checksum}
        assert manager._verify_checksums(tmp_path, checksums) is False

    def test_verify_checksums_fails_on_missing_file(self, backup_db_session, tmp_path):
        """Test checksum verification fails if expected file is missing.

        ARRANGE: Create checksums for non-existent file
        ACT: Verify checksums
        ASSERT: Verification should fail

        Tests that verification detects missing files.
        """
        manager = BackupManager(backup_db_session)

        # ACT & ASSERT
        checksums = {"missing.txt": "sha256:abc123"}
        assert manager._verify_checksums(tmp_path, checksums) is False


@pytest.mark.integration
class TestBackupManagerPathOperations:
    """Integration tests for backup path operations."""

    def test_get_backup_dir_returns_correct_path_structure(
        self, backup_db_session, backup_test_config
    ):
        """Test backup directory path generation follows app structure.

        ARRANGE: Set up test config
        ACT: Get backup directory path
        ASSERT: Path contains correct app name and backup ID

        Tests that backup paths are organized correctly.
        """
        manager = BackupManager(backup_db_session)

        backup_dir = manager._get_backup_dir("my-app", "20251030_143022_a8f3d9")

        assert backup_dir.parts[-3:] == ("apps", "my-app", "20251030_143022_a8f3d9")
        assert "backups" in str(backup_dir)

    def test_get_hop3_version_returns_string(self, backup_db_session):
        """Test version retrieval returns valid string.

        ARRANGE: Create manager
        ACT: Get Hop3 version
        ASSERT: Should return non-empty string

        Tests that version can be retrieved.
        """
        manager = BackupManager(backup_db_session)

        version = manager._get_hop3_version()

        assert isinstance(version, str)
        assert len(version) > 0


@pytest.mark.integration
class TestBackupManagerServiceDetection:
    """Integration tests for attached addon/service detection."""

    def test_detect_attached_postgres_from_database_url(
        self, backup_db_session, sample_app
    ):
        """Test PostgreSQL detection from DATABASE_URL env var.

        ARRANGE: Create app with PostgreSQL environment variable
        ACT: Get attached addons
        ASSERT: Should detect postgres service

        Tests that backup system discovers attached services correctly.
        """
        manager = BackupManager(backup_db_session)
        # sample_app already has env vars, but we need to add DATABASE_URL
        db_env = EnvVar(
            name="DATABASE_URL",
            value="postgresql://user:pass@localhost/mydb",
            app=sample_app,
        )
        backup_db_session.add(db_env)
        backup_db_session.commit()

        services = manager._get_attached_addons(sample_app)

        assert len(services) == 1
        assert services[0] == ("postgres", "mydb")

    def test_detect_no_services_when_no_database_url(
        self, backup_db_session, sample_app
    ):
        """Test that services list is empty when no services attached.

        ARRANGE: Create app with standard env vars (no database)
        ACT: Get attached addons
        ASSERT: Should return empty list

        Tests that detection doesn't produce false positives.
        """
        manager = BackupManager(backup_db_session)

        services = manager._get_attached_addons(sample_app)

        assert len(services) == 0


@pytest.mark.integration
class TestBackupManagerDatabaseStateChanges:
    """Integration tests verifying actual database state changes."""

    def test_create_backup_creates_database_record(
        self, backup_db_session, sample_app, backup_test_config
    ):
        """Test backup creation persists backup record to database.

        ARRANGE: Set up app and manager
        ACT: Create backup
        ASSERT: Backup record should exist in database

        Tests that backups are properly tracked in database.
        """
        manager = BackupManager(backup_db_session)

        # (we mock only the addon backup to avoid external service dependencies)
        with patch("hop3.core.backup.get_addon"):
            _backup_id, _backup_dir = manager.create_backup(
                sample_app, include_addons=False
            )

        backup_records = backup_db_session.query(Backup).all()
        assert len(backup_records) > 0

        # Find the created backup
        backup = next((b for b in backup_records if sample_app.id == b.app_id), None)
        assert backup is not None
        assert backup.state == BackupStateEnum.COMPLETED
        assert backup.format == "tgz"
        assert backup.size > 0

    def test_backup_record_state_transitions(
        self, backup_db_session, sample_app, backup_test_config
    ):
        """Test backup record transitions through correct states.

        ARRANGE: Create app and backup manager
        ACT: Create backup and observe state changes
        ASSERT: State should transition from STARTED to COMPLETED

        Tests state machine correctness for backups.
        """
        manager = BackupManager(backup_db_session)

        # (we mock only addon backup to avoid external service dependencies)
        with patch("hop3.core.backup.get_addon"):
            _backup_id, _ = manager.create_backup(sample_app, include_addons=False)

        backup = backup_db_session.query(Backup).filter_by(app_id=sample_app.id).first()
        assert backup is not None
        assert backup.state == BackupStateEnum.COMPLETED

    def test_backup_record_failure_state(
        self, backup_db_session, sample_app, backup_test_config
    ):
        """Test backup record transitions to FAILED on error.

        ARRANGE: Create app, mock tar failure
        ACT: Attempt backup that fails
        ASSERT: Record state should be FAILED

        Tests error handling and state rollback.
        """
        manager = BackupManager(backup_db_session)

        with (
            patch("hop3.core.backup.tarfile.open", side_effect=Exception("Mock error")),
            pytest.raises(RuntimeError),
        ):
            manager.create_backup(sample_app, include_addons=False)

        backup = backup_db_session.query(Backup).filter_by(app_id=sample_app.id).first()
        assert backup is not None
        assert backup.state == BackupStateEnum.FAILED
