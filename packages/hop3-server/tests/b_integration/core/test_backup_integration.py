# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
State-based integration tests for backup functionality.

These tests verify the BackupManager with real database state changes
and mock only external I/O boundaries (file system operations for
tar/backup files, subprocess if used).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import tarfile
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hop3.config import HopConfig
from hop3.core.backup import BackupManager, BackupManifest
from hop3.deployers.volumes import realize_volumes
from hop3.orm import AddonCredential, App, Backup, BackupStateEnum, EnvVar
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
)
from hop3.orm.session import BigIntAuditBase


@pytest.fixture
def backup_db_engine():
    """
    Create fresh in-memory test database for backup tests.

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
    """
    Create database session for backup tests.

    Provides fresh session for querying test state.

    Args:
        backup_db_engine: Fresh in-memory database engine

    Yields:
        SQLAlchemy Session for database operations
    """
    SessionLocal = sessionmaker(bind=backup_db_engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def backup_repo(backup_db_session):
    """Create a BackupRepository for testing."""
    return BackupRepository(session=backup_db_session)


@pytest.fixture
def app_repo(backup_db_session):
    """Create an AppRepository for testing."""
    return AppRepository(session=backup_db_session)


@pytest.fixture
def addon_credential_repo(backup_db_session):
    """Create an AddonCredentialRepository for testing."""
    return AddonCredentialRepository(session=backup_db_session)


@pytest.fixture
def backup_manager(backup_repo, app_repo, addon_credential_repo):
    """Create a BackupManager with repositories for testing."""
    return BackupManager(
        backup_repo=backup_repo,
        app_repo=app_repo,
        addon_credential_repo=addon_credential_repo,
    )


@pytest.fixture
def backup_test_config(tmp_path):
    """
    Configure Hop3 with test directories.

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
    """
    Create test application with files and environment variables.

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
        """
        Test creating a manifest captures all required fields.

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
        """
        Test JSON serialization roundtrip persists manifest state.

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
        with pathlib.Path(manifest_file).open() as f:
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

    def test_manager_initialization_stores_session(
        self, backup_repo, app_repo, addon_credential_repo
    ):
        """
        Test BackupManager initializes with repositories.

        ARRANGE: Create manager with repositories
        ACT: Access repositories
        ASSERT: Verify repositories are stored

        Tests that manager correctly stores repository references.
        """
        manager = BackupManager(
            backup_repo=backup_repo,
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
        )

        # ACT & ASSERT
        assert manager.backup_repo == backup_repo
        assert manager.app_repo == app_repo
        assert manager.addon_credential_repo == addon_credential_repo

    def test_generate_backup_id_creates_valid_format(self, backup_manager):
        """
        Test backup ID generation follows correct format.

        ARRANGE: Create manager and generate ID
        ACT: Parse generated ID
        ASSERT: Verify format is YYYYMMDD_HHMMSS_XXXXXX

        Tests that backup IDs are properly formatted for parsing.
        """
        backup_id = backup_manager._generate_backup_id()

        parts = backup_id.split("_")
        assert len(parts) == 3, f"Expected 3 parts, got {len(parts)}"
        assert len(parts[0]) == 8, "Date should be YYYYMMDD (8 chars)"
        assert len(parts[1]) == 6, "Time should be HHMMSS (6 chars)"
        assert len(parts[2]) == 6, "Random suffix should be 6 hex chars"

    def test_generate_backup_ids_are_unique(self, backup_manager):
        """
        Test that multiple backup IDs are unique.

        ARRANGE: Generate multiple IDs
        ACT: Add to set to check uniqueness
        ASSERT: All IDs should be different

        Tests that randomness ensures unique IDs even in rapid succession.
        """
        ids = {backup_manager._generate_backup_id() for _ in range(10)}

        assert len(ids) == 10, "Not all backup IDs were unique"

    def test_calculate_checksum_produces_sha256_format(self, backup_manager, tmp_path):
        """
        Test checksum calculation produces valid SHA256 format.

        ARRANGE: Create test file with content
        ACT: Calculate checksum
        ASSERT: Verify SHA256 format and consistency

        Tests that checksums are properly formatted and deterministic.
        """
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        checksum = backup_manager._calculate_checksum(test_file)

        assert checksum.startswith("sha256:")
        assert len(checksum) == 71  # "sha256:" (7) + 64 hex chars

    def test_calculate_checksum_is_deterministic(self, backup_manager, tmp_path):
        """
        Test that same file content produces same checksum.

        ARRANGE: Create test file
        ACT: Calculate checksum twice
        ASSERT: Checksums should match

        Tests that checksum calculation is deterministic.
        """
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        checksum1 = backup_manager._calculate_checksum(test_file)
        checksum2 = backup_manager._calculate_checksum(test_file)

        assert checksum1 == checksum2

    def test_calculate_checksum_differs_for_different_content(
        self, backup_manager, tmp_path
    ):
        """
        Test different file content produces different checksums.

        ARRANGE: Create two files with different content
        ACT: Calculate checksums for each
        ASSERT: Checksums should differ

        Tests checksum correctness for different content.
        """
        file1 = tmp_path / "test1.txt"
        file2 = tmp_path / "test2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")

        checksum1 = backup_manager._calculate_checksum(file1)
        checksum2 = backup_manager._calculate_checksum(file2)

        assert checksum1 != checksum2

    def test_verify_checksums_succeeds_for_valid_files(self, backup_manager, tmp_path):
        """
        Test checksum verification passes for valid backup files.

        ARRANGE: Create files and calculate their checksums
        ACT: Verify checksums
        ASSERT: Verification should pass

        Tests that verification correctly validates backup integrity.
        """
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")

        checksums = {
            "file1.txt": backup_manager._calculate_checksum(file1),
            "file2.txt": backup_manager._calculate_checksum(file2),
        }

        # ACT & ASSERT
        assert backup_manager._verify_checksums(tmp_path, checksums) is True

    def test_verify_checksums_fails_on_corrupted_file(self, backup_manager, tmp_path):
        """
        Test checksum verification fails when file is modified.

        ARRANGE: Create file, calculate checksum, then modify it
        ACT: Verify checksums
        ASSERT: Verification should fail

        Tests that verification detects file corruption.
        """
        test_file = tmp_path / "test.txt"
        test_file.write_text("Original content")

        checksum = backup_manager._calculate_checksum(test_file)

        test_file.write_text("Modified content")

        checksums = {"test.txt": checksum}
        assert backup_manager._verify_checksums(tmp_path, checksums) is False

    def test_verify_checksums_fails_on_missing_file(self, backup_manager, tmp_path):
        """
        Test checksum verification fails if expected file is missing.

        ARRANGE: Create checksums for non-existent file
        ACT: Verify checksums
        ASSERT: Verification should fail

        Tests that verification detects missing files.
        """
        # ACT & ASSERT
        checksums = {"missing.txt": "sha256:abc123"}
        assert backup_manager._verify_checksums(tmp_path, checksums) is False


@pytest.mark.integration
class TestBackupManagerPathOperations:
    """Integration tests for backup path operations."""

    def test_get_backup_dir_returns_correct_path_structure(
        self, backup_manager, backup_test_config
    ):
        """
        Test backup directory path generation follows app structure.

        ARRANGE: Set up test config
        ACT: Get backup directory path
        ASSERT: Path contains correct app name and backup ID

        Tests that backup paths are organized correctly.
        """
        backup_dir = backup_manager._get_backup_dir("my-app", "20251030_143022_a8f3d9")

        assert backup_dir.parts[-3:] == ("apps", "my-app", "20251030_143022_a8f3d9")
        assert "backups" in str(backup_dir)

    def test_get_hop3_version_returns_string(self, backup_manager):
        """
        Test version retrieval returns valid string.

        ARRANGE: Create manager
        ACT: Get Hop3 version
        ASSERT: Should return non-empty string

        Tests that version can be retrieved.
        """
        version = backup_manager._get_hop3_version()

        assert isinstance(version, str)
        assert len(version) > 0


@pytest.mark.integration
class TestBackupManagerServiceDetection:
    """Integration tests for attached addon/service detection."""

    def test_detect_attached_postgres_from_addon_credential(
        self, backup_db_session, backup_manager, sample_app
    ):
        """
        Test PostgreSQL detection from AddonCredential record.

        ARRANGE: Create app with attached PostgreSQL addon
        ACT: Get attached addons
        ASSERT: Should detect postgres service

        Tests that backup system discovers attached services correctly.
        """
        # Create an AddonCredential record for the postgres addon
        credential = AddonCredential(
            app_id=sample_app.id,
            addon_type="postgres",
            addon_name="mydb",
            encrypted_data="dummy_encrypted_data",
        )
        backup_db_session.add(credential)
        backup_db_session.commit()

        services = backup_manager._get_attached_addons(sample_app)

        assert len(services) == 1
        assert services[0] == ("postgres", "mydb")

    def test_detect_no_services_when_no_database_url(self, backup_manager, sample_app):
        """
        Test that services list is empty when no services attached.

        ARRANGE: Create app with standard env vars (no database)
        ACT: Get attached addons
        ASSERT: Should return empty list

        Tests that detection doesn't produce false positives.
        """
        services = backup_manager._get_attached_addons(sample_app)

        assert len(services) == 0


@pytest.mark.integration
class TestBackupManagerDatabaseStateChanges:
    """Integration tests verifying actual database state changes."""

    def test_create_backup_creates_database_record(
        self, backup_db_session, backup_manager, sample_app, backup_test_config
    ):
        """
        Test backup creation persists backup record to database.

        ARRANGE: Set up app and manager
        ACT: Create backup
        ASSERT: Backup record should exist in database

        Tests that backups are properly tracked in database.
        """
        # (we mock only the addon backup to avoid external service dependencies)
        with patch("hop3.core.backup.get_addon"):
            _backup_id, _backup_dir = backup_manager.create_backup(
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
        self, backup_db_session, backup_manager, sample_app, backup_test_config
    ):
        """
        Test backup record transitions through correct states.

        ARRANGE: Create app and backup manager
        ACT: Create backup and observe state changes
        ASSERT: State should transition from STARTED to COMPLETED

        Tests state machine correctness for backups.
        """
        # (we mock only addon backup to avoid external service dependencies)
        with patch("hop3.core.backup.get_addon"):
            _backup_id, _ = backup_manager.create_backup(
                sample_app, include_addons=False
            )

        backup = backup_db_session.query(Backup).filter_by(app_id=sample_app.id).first()
        assert backup is not None
        assert backup.state == BackupStateEnum.COMPLETED

    def test_backup_record_failure_state(
        self, backup_db_session, backup_manager, sample_app, backup_test_config
    ):
        """
        Test backup record transitions to FAILED on error.

        ARRANGE: Create app, mock tar failure
        ACT: Attempt backup that fails
        ASSERT: Record state should be FAILED

        Tests error handling and state rollback.
        """
        with (
            patch("hop3.core.backup.tarfile.open", side_effect=Exception("Mock error")),
            pytest.raises(RuntimeError),
        ):
            backup_manager.create_backup(sample_app, include_addons=False)

        backup = backup_db_session.query(Backup).filter_by(app_id=sample_app.id).first()
        assert backup is not None
        assert backup.state == BackupStateEnum.FAILED


@pytest.mark.integration
class TestVolumeBackupRestore:
    """
    Backups must include [[volumes]] data and restore it (ADR 046 §2).

    Regression for the audit's two critical backup findings: (1) volume data was
    silently excluded from backups, and (2) the in-src volume symlink made
    restore abort with AbsoluteLinkError for the whole app.
    """

    def test_volume_data_is_backed_up_and_restored(self, backup_manager, sample_app):

        app = sample_app
        # Declare a volume and realize it, then write a sentinel through the link.
        (app.src_path / "hop3.toml").write_text(
            '[[volumes]]\nname = "store"\ntarget = "data/store"\n'
        )
        realize_volumes(
            app, [{"name": "store", "target": "data/store", "type": "persist"}]
        )
        (app.src_path / "data" / "store" / "secret.txt").write_text("precious")
        assert (app.volumes_path / "store" / "secret.txt").read_text() == "precious"

        # Backup includes the volume as its own member; the manifest records it.
        _backup_id, backup_dir = backup_manager.create_backup(app, include_addons=False)
        manifest = BackupManifest.from_file(backup_dir / "metadata.json")
        assert any(v["name"] == "store" for v in manifest.volumes)
        assert (backup_dir / "volume-store.tar.gz").exists()
        assert "volume-store.tar.gz" in manifest.checksums  # integrity-checked

        # The in-src symlink must NOT be in source.tar.gz (else restore aborts).
        with tarfile.open(backup_dir / "source.tar.gz") as tar:
            assert "src/data/store" not in tar.getnames()

        # Simulate the live app being gone, then restore the file-level pieces.
        shutil.rmtree(app.volumes_path)
        shutil.rmtree(app.src_path)
        backup_manager._restore_source(app, backup_dir)  # must NOT raise
        backup_manager._restore_volumes(app, backup_dir, manifest)

        assert (app.volumes_path / "store" / "secret.txt").read_text() == "precious"

    def test_volume_backup_can_be_opted_out(self, backup_manager, sample_app):

        app = sample_app
        (app.src_path / "hop3.toml").write_text(
            '[[volumes]]\nname = "store"\ntarget = "data/store"\n'
            "[volumes.backup]\ninclude = false\n"
        )
        realize_volumes(
            app, [{"name": "store", "target": "data/store", "type": "persist"}]
        )
        (app.src_path / "data" / "store" / "x.txt").write_text("data")

        _id, backup_dir = backup_manager.create_backup(app, include_addons=False)
        manifest = BackupManifest.from_file(backup_dir / "metadata.json")
        assert manifest.volumes == []  # opted out, not archived
        assert not (backup_dir / "volume-store.tar.gz").exists()

    def test_backup_without_volumes_is_unaffected(self, backup_manager, sample_app):
        # An app with no [[volumes]] backs up exactly as before (no volume files).

        _id, backup_dir = backup_manager.create_backup(sample_app, include_addons=False)
        manifest = BackupManifest.from_file(backup_dir / "metadata.json")
        assert manifest.volumes == []
        assert not list(backup_dir.glob("volume-*.tar.gz"))

    def test_unreadable_config_fails_the_backup_loudly(
        self, backup_db_session, backup_manager, sample_app
    ):
        # H1 regression: a malformed hop3.toml must abort the backup, not
        # silently omit the app's volume data while reporting success.
        app = sample_app
        realize_volumes(
            app, [{"name": "store", "target": "data/store", "type": "persist"}]
        )
        (app.src_path / "data" / "store" / "secret.txt").write_text("precious")
        # Invalid TOML: the loader must raise rather than yield "no volumes".
        (app.src_path / "hop3.toml").write_text('[[volumes]]\nname = "store"\ntarget =')

        with pytest.raises(RuntimeError):
            backup_manager.create_backup(app, include_addons=False)

        backup = backup_db_session.query(Backup).filter_by(app_id=app.id).first()
        assert backup is not None
        assert backup.state == BackupStateEnum.FAILED

    def test_restore_fails_loud_when_volume_archive_missing(
        self, backup_manager, sample_app
    ):
        # Restore-side twin of H1: the manifest says a volume was backed up,
        # but its archive is absent. Continuing would let the later deploy
        # re-seed the volume EMPTY and report success — silent data loss.
        app = sample_app
        manifest = BackupManifest(
            backup_id="x",
            app_name=app.name,
            created_at="2026-01-01T00:00:00Z",
            format_version="1.0",
            hop3_version="test",
            size_bytes=0,
            checksums={},
            app_metadata={},
            addons=[],
            env_vars_count=0,
            expires_after=0,
            volumes=[{"name": "store", "backup_file": "volume-store.tar.gz"}],
        )
        # app.app_path has no volume-store.tar.gz, so the declared archive is
        # missing — restore must abort rather than silently skip it.
        with pytest.raises(FileNotFoundError):
            backup_manager._restore_volumes(app, app.app_path, manifest)


@pytest.mark.integration
class TestBackupPathsExclude:
    """[backup].exclude prunes the source/data archives; [backup].paths adds dirs."""

    def _write_src(self, app):
        """Populate the app's source tree with keep/junk/cache/uploads files."""
        (app.src_path / "hop3.toml").write_text(
            '[backup]\npaths = ["uploads"]\nexclude = ["*.tmp", "cache"]\n'
        )
        (app.src_path / "keep.py").write_text("print('keep')")
        (app.src_path / "junk.tmp").write_text("junk")
        (app.src_path / "cache").mkdir()
        (app.src_path / "cache" / "big.bin").write_text("x" * 100)
        (app.src_path / "uploads").mkdir()
        (app.src_path / "uploads" / "file.dat").write_text("user content")

    def test_exclude_prunes_source_and_paths_archives_extra(
        self, backup_manager, sample_app
    ):
        app = sample_app
        self._write_src(app)

        _id, backup_dir = backup_manager.create_backup(app, include_addons=False)
        manifest = BackupManifest.from_file(backup_dir / "metadata.json")

        with tarfile.open(backup_dir / "source.tar.gz") as tar:
            names = set(tar.getnames())
        assert "src/keep.py" in names
        assert "src/uploads/file.dat" in names  # not excluded → in source too
        assert "src/junk.tmp" not in names  # *.tmp pruned
        assert "src/cache" not in names  # 'cache' segment pruned (dir + contents)
        assert "src/cache/big.bin" not in names

        # [backup].paths captured uploads/ as its own member + manifest entry.
        assert (backup_dir / "extra.tar.gz").exists()
        assert "extra.tar.gz" in manifest.checksums  # integrity-checked
        assert "src/uploads" in manifest.extra_paths
        with tarfile.open(backup_dir / "extra.tar.gz") as tar:
            assert "src/uploads/file.dat" in tar.getnames()

    def test_restore_roundtrips_excluded_and_extra(self, backup_manager, sample_app):
        app = sample_app
        self._write_src(app)
        _id, backup_dir = backup_manager.create_backup(app, include_addons=False)
        manifest = BackupManifest.from_file(backup_dir / "metadata.json")

        shutil.rmtree(app.src_path)
        backup_manager._restore_source(app, backup_dir)
        backup_manager._restore_extra(app, backup_dir, manifest)

        assert (app.src_path / "keep.py").exists()
        assert (app.src_path / "uploads" / "file.dat").read_text() == "user content"
        assert not (app.src_path / "junk.tmp").exists()  # stayed pruned
        assert not (app.src_path / "cache").exists()

    def test_no_backup_section_is_unaffected(self, backup_manager, sample_app):
        # An app with no [backup] section produces no extra.tar.gz.
        _id, backup_dir = backup_manager.create_backup(sample_app, include_addons=False)
        manifest = BackupManifest.from_file(backup_dir / "metadata.json")
        assert manifest.extra_paths == []
        assert not (backup_dir / "extra.tar.gz").exists()

    def test_path_escaping_app_tree_fails_loud(
        self, backup_db_session, backup_manager, sample_app
    ):
        app = sample_app
        (app.src_path / "hop3.toml").write_text('[backup]\npaths = ["../../etc"]\n')

        with pytest.raises(RuntimeError):
            backup_manager.create_backup(app, include_addons=False)

        backup = backup_db_session.query(Backup).filter_by(app_id=app.id).first()
        assert backup is not None
        assert backup.state == BackupStateEnum.FAILED

    def test_path_through_symlink_outside_tree_fails_loud(
        self, backup_db_session, backup_manager, sample_app, tmp_path
    ):
        # An in-tree symlink to an external dir must not let a backup read
        # outside the app subtree (realpath confinement, not lexical).
        app = sample_app
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("should never be archived")
        (app.src_path / "escape").symlink_to(outside)
        (app.src_path / "hop3.toml").write_text('[backup]\npaths = ["escape"]\n')

        with pytest.raises(RuntimeError):
            backup_manager.create_backup(app, include_addons=False)

        backup = backup_db_session.query(Backup).filter_by(app_id=app.id).first()
        assert backup.state == BackupStateEnum.FAILED
