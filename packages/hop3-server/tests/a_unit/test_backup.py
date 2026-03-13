# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for backup functionality."""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock

from hop3.core.backup import BackupManager, BackupManifest, format_size


def create_backup_manager_with_mocks():
    """Create a BackupManager with mocked repositories."""
    mock_backup_repo = MagicMock()
    mock_app_repo = MagicMock()
    mock_addon_credential_repo = MagicMock()
    return BackupManager(
        backup_repo=mock_backup_repo,
        app_repo=mock_app_repo,
        addon_credential_repo=mock_addon_credential_repo,
    )


class TestBackupManifest:
    """Test BackupManifest dataclass."""

    def test_create_manifest(self):
        """Test creating a manifest."""
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
                    "backup_file": "services/postgres_test-db.sql",
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

    def test_to_json(self):
        """Test converting manifest to JSON."""
        manifest = BackupManifest(
            backup_id="test_backup",
            app_name="test-app",
            created_at="2025-10-30T14:30:22Z",
            format_version="1.0",
            hop3_version="0.8.0",
            size_bytes=1024,
            checksums={},
            app_metadata={},
            addons=[],
            env_vars_count=0,
            expires_after=0,
        )

        data = manifest.to_json()

        assert isinstance(data, dict)
        assert data["backup_id"] == "test_backup"
        assert data["app_name"] == "test-app"

    def test_from_json(self):
        """Test creating manifest from JSON."""
        data = {
            "backup_id": "test_backup",
            "app_name": "test-app",
            "created_at": "2025-10-30T14:30:22Z",
            "format_version": "1.0",
            "hop3_version": "0.8.0",
            "size_bytes": 1024,
            "checksums": {},
            "app_metadata": {},
            "addons": [],
            "env_vars_count": 0,
            "expires_after": 0,
        }

        manifest = BackupManifest.from_json(data)

        assert manifest.backup_id == "test_backup"
        assert manifest.app_name == "test-app"

    def test_roundtrip(self):
        """Test JSON serialization roundtrip."""
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

        # Serialize and deserialize
        data = original.to_json()
        restored = BackupManifest.from_json(data)

        assert restored.backup_id == original.backup_id
        assert restored.app_name == original.app_name
        assert restored.size_bytes == original.size_bytes
        assert restored.checksums == original.checksums
        assert restored.addons == original.addons


class TestBackupManager:
    """Test BackupManager class."""

    def test_init(self):
        """Test BackupManager initialization."""
        mock_backup_repo = MagicMock()
        mock_app_repo = MagicMock()
        mock_addon_credential_repo = MagicMock()
        manager = BackupManager(
            backup_repo=mock_backup_repo,
            app_repo=mock_app_repo,
            addon_credential_repo=mock_addon_credential_repo,
        )

        assert manager.backup_repo == mock_backup_repo
        assert manager.app_repo == mock_app_repo
        assert manager.addon_credential_repo == mock_addon_credential_repo

    def test_generate_backup_id(self):
        """Test backup ID generation."""
        manager = create_backup_manager_with_mocks()

        backup_id = manager._generate_backup_id()

        # Should be in format: YYYYMMDD_HHMMSS_<random>
        parts = backup_id.split("_")
        assert len(parts) == 3
        assert len(parts[0]) == 8  # YYYYMMDD
        assert len(parts[1]) == 6  # HHMMSS
        assert len(parts[2]) == 6  # Random hex

    def test_generate_unique_backup_ids(self):
        """Test that backup IDs are unique."""
        manager = create_backup_manager_with_mocks()

        ids = {manager._generate_backup_id() for _ in range(10)}

        # All IDs should be unique
        assert len(ids) == 10

    def test_calculate_checksum(self, tmp_path):
        """Test checksum calculation."""
        manager = create_backup_manager_with_mocks()

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        checksum = manager._calculate_checksum(test_file)

        # Should be sha256 format
        assert checksum.startswith("sha256:")
        assert len(checksum) == 71  # "sha256:" + 64 hex chars

        # Same content should give same checksum
        checksum2 = manager._calculate_checksum(test_file)
        assert checksum == checksum2

    def test_calculate_checksum_different_content(self, tmp_path):
        """Test that different content gives different checksums."""
        manager = create_backup_manager_with_mocks()

        file1 = tmp_path / "test1.txt"
        file2 = tmp_path / "test2.txt"

        file1.write_text("Content 1")
        file2.write_text("Content 2")

        checksum1 = manager._calculate_checksum(file1)
        checksum2 = manager._calculate_checksum(file2)

        assert checksum1 != checksum2

    def test_verify_checksums(self, tmp_path):
        """Test checksum verification."""
        manager = create_backup_manager_with_mocks()

        # Create test files
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("Content 1")
        file2.write_text("Content 2")

        # Calculate checksums
        checksums = {
            "file1.txt": manager._calculate_checksum(file1),
            "file2.txt": manager._calculate_checksum(file2),
        }

        # Verify should pass
        assert manager._verify_checksums(tmp_path, checksums)

    def test_verify_checksums_fails_on_mismatch(self, tmp_path):
        """Test that verification fails on checksum mismatch."""
        manager = create_backup_manager_with_mocks()

        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Original content")

        # Calculate checksum
        checksum = manager._calculate_checksum(test_file)

        # Modify file
        test_file.write_text("Modified content")

        # Verify should fail
        checksums = {"test.txt": checksum}
        assert not manager._verify_checksums(tmp_path, checksums)

    def test_verify_checksums_fails_on_missing_file(self, tmp_path):
        """Test that verification fails if file is missing."""
        manager = create_backup_manager_with_mocks()

        # Create checksums for non-existent file
        checksums = {"missing.txt": "sha256:abc123"}

        # Verify should fail
        assert not manager._verify_checksums(tmp_path, checksums)

    def test_get_backup_dir(self):
        """Test backup directory path generation."""
        manager = create_backup_manager_with_mocks()

        backup_dir = manager._get_backup_dir("my-app", "20251030_143022_a8f3d9")

        # Should be under BACKUP_ROOT/apps/app-name/backup-id
        assert backup_dir.parts[-3:] == ("apps", "my-app", "20251030_143022_a8f3d9")
        assert "backups" in str(backup_dir)

    def test_get_hop3_version(self):
        """Test getting Hop3 version."""
        manager = create_backup_manager_with_mocks()

        version = manager._get_hop3_version()

        # Should return a string (could be "unknown" if not installed)
        assert isinstance(version, str)

    def test_get_attached_addons_postgres(self):
        """Test service discovery for PostgreSQL via AddonCredential."""
        mock_backup_repo = MagicMock()
        mock_app_repo = MagicMock()
        mock_addon_credential_repo = MagicMock()

        # Create mock app
        mock_app = MagicMock()
        mock_app.id = 1

        # Mock AddonCredential get_by_app_id result
        mock_credential = MagicMock()
        mock_credential.addon_type = "postgres"
        mock_credential.addon_name = "mydb"
        mock_addon_credential_repo.get_by_app_id.return_value = [mock_credential]

        manager = BackupManager(
            backup_repo=mock_backup_repo,
            app_repo=mock_app_repo,
            addon_credential_repo=mock_addon_credential_repo,
        )

        services = manager._get_attached_addons(mock_app)

        assert len(services) == 1
        assert services[0] == ("postgres", "mydb")

    def test_get_attached_addons_none(self):
        """Test service discovery with no services."""
        mock_backup_repo = MagicMock()
        mock_app_repo = MagicMock()
        mock_addon_credential_repo = MagicMock()

        # Create mock app with no attached addons
        mock_app = MagicMock()
        mock_app.id = 1
        mock_addon_credential_repo.get_by_app_id.return_value = []

        manager = BackupManager(
            backup_repo=mock_backup_repo,
            app_repo=mock_app_repo,
            addon_credential_repo=mock_addon_credential_repo,
        )

        services = manager._get_attached_addons(mock_app)

        assert len(services) == 0

    def test_manifest_file_operations(self, tmp_path):
        """Test reading and writing manifest files."""
        manifest = BackupManifest(
            backup_id="test_backup",
            app_name="test-app",
            created_at="2025-10-30T14:30:22Z",
            format_version="1.0",
            hop3_version="0.8.0",
            size_bytes=1024,
            checksums={"file.tar.gz": "sha256:abc123"},
            app_metadata={"hostname": "test.example.com"},
            addons=[],
            env_vars_count=5,
            expires_after=0,
        )

        # Write to file
        manifest_file = tmp_path / "metadata.json"
        manifest.to_file(manifest_file)

        # File should exist and be valid JSON
        assert manifest_file.exists()
        with pathlib.Path(manifest_file).open() as f:
            data = json.load(f)
            assert data["backup_id"] == "test_backup"

        # Read back from file
        restored = BackupManifest.from_file(manifest_file)

        assert restored.backup_id == manifest.backup_id
        assert restored.app_name == manifest.app_name
        assert restored.checksums == manifest.checksums


def test_format_size():
    """Test size formatting."""

    assert format_size(500) == "500.0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
    assert format_size(1024 * 1024 * 1024) == "1.0 GB"
    assert format_size(1536) == "1.5 KB"
