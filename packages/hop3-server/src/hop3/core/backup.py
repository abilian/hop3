# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Backup and restore functionality for Hop3 applications.

This module provides the BackupManager class for creating and restoring
complete application backups including source code, data, environment
variables, and attached addons.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import secrets
import shutil
import tarfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hop3.config import HopConfig
from hop3.core.plugins import get_addon
from hop3.lib import log
from hop3.orm import App, Backup, BackupStateEnum, EnvVar
from hop3.orm.repositories import AppRepository


def format_size(size_bytes: float) -> str:
    """Format byte size as human-readable string.

    Args:
        size_bytes: Size in bytes (accepts int or float)

    Returns:
        Formatted string like "1.5 MB"

    Examples:
        >>> format_size(1024)
        '1.0 KB'
        >>> format_size(1536)
        '1.5 KB'
        >>> format_size(1048576)
        '1.0 MB'
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class BackupManifest:
    """Represents a backup's metadata.

    This dataclass contains all information about a backup including
    what was backed up, when, sizes, checksums, and how to restore it.
    """

    backup_id: str
    app_name: str
    created_at: str  # ISO format timestamp
    format_version: str
    hop3_version: str
    size_bytes: int
    checksums: dict[str, str]
    app_metadata: dict[str, Any]
    addons: list[dict[str, Any]]
    env_vars_count: int
    expires_after: int

    @classmethod
    def from_json(cls, data: dict) -> BackupManifest:
        """Load manifest from JSON data.

        Args:
            data: Dictionary loaded from JSON

        Returns:
            BackupManifest instance
        """
        return cls(**data)

    def to_json(self) -> dict:
        """Convert manifest to JSON-serializable dict.

        Returns:
            Dictionary that can be serialized to JSON
        """
        return asdict(self)

    @classmethod
    def from_file(cls, path: Path) -> BackupManifest:
        """Load manifest from a JSON file.

        Args:
            path: Path to metadata.json file

        Returns:
            BackupManifest instance
        """
        with path.open() as f:
            data = json.load(f)
        return cls.from_json(data)

    def to_file(self, path: Path) -> None:
        """Write manifest to a JSON file.

        Args:
            path: Path where to write metadata.json
        """
        with path.open("w") as f:
            json.dump(self.to_json(), f, indent=2)


class BackupManager:
    """Manages backup and restore operations for applications.

    This class handles creating full backups of applications including:
    - Source code (git repository)
    - Application data directory
    - Environment variables
    - Attached addons (databases, caches, etc.)

    All backups are stored in /var/hop3/backups/apps/<app-name>/<backup-id>/
    """

    def __init__(self, db_session: Session):
        """Initialize the backup manager.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db_session = db_session

    def create_backup(
        self, app: App, *, include_addons: bool = True
    ) -> tuple[str, Path]:
        """Create a backup of an application.

        Args:
            app: Application to backup
            include_addons: Whether to include attached services

        Returns:
            Tuple of (backup_id, backup_path)

        Raises:
            RuntimeError: If backup creation fails
        """
        backup_id = self._generate_backup_id()
        backup_dir = self._get_backup_dir(app.name, backup_id)

        # Create backup directory
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create database record
        backup_record = Backup(
            app_id=app.id,
            state=BackupStateEnum.STARTED,
            format="tgz",
            remote_path=str(backup_dir),
            size=0,
            expires_after=0,
        )
        self.db_session.add(backup_record)
        self.db_session.commit()

        try:
            # Backup components
            # FIXME: not used
            source_info = self._backup_source(app, backup_dir)
            data_info = self._backup_data(app, backup_dir)
            env_info = self._backup_env(app, backup_dir)

            addons_info = []
            if include_addons:
                addons_info = self._backup_addons(app, backup_dir)

            # Create checksums
            checksums = {}
            for filename in ["source.tar.gz", "data.tar.gz", "env.json"]:
                file_path = backup_dir / filename
                if file_path.exists():
                    checksums[filename] = self._calculate_checksum(file_path)

            for service_info in addons_info:
                service_file = backup_dir / service_info["backup_file"]
                if service_file.exists():
                    checksums[service_info["backup_file"]] = self._calculate_checksum(
                        service_file
                    )

            # Calculate total size
            total_size = sum(
                (backup_dir / f).stat().st_size
                for f in backup_dir.iterdir()
                if f.is_file()
            )

            # Create manifest
            manifest = BackupManifest(
                backup_id=backup_id,
                app_name=app.name,
                created_at=datetime.now(timezone.utc).isoformat(),
                format_version="1.0",
                hop3_version=self._get_hop3_version(),
                size_bytes=total_size,
                checksums=checksums,
                app_metadata={
                    "hostname": app.hostname,
                    "port": app.port,
                    "run_state": app.run_state.name,
                },
                addons=addons_info,
                env_vars_count=len(app.env_vars),
                expires_after=0,
            )

            # Write manifest
            manifest.to_file(backup_dir / "metadata.json")

            # Update database record
            backup_record.state = BackupStateEnum.COMPLETED
            backup_record.size = total_size
            self.db_session.commit()

            log(f"Backup created successfully: {backup_id}")

            return backup_id, backup_dir

        except Exception as e:
            # Mark as failed and clean up
            backup_record.state = BackupStateEnum.FAILED
            self.db_session.commit()

            # Try to remove partial backup
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

            msg = f"Backup creation failed: {e}"
            raise RuntimeError(msg) from e

    def restore_backup(
        self, backup_id: str, target_app_name: str | None = None
    ) -> None:
        """Restore an application from backup.

        Args:
            backup_id: ID of backup to restore
            target_app_name: Optional different app name to restore to

        Raises:
            RuntimeError: If restore fails
            FileNotFoundError: If backup not found
        """
        # Find backup in database
        backup_record = (
            self.db_session
            .query(Backup)
            .join(App)
            .filter(Backup.remote_path.contains(backup_id))
            .first()
        )

        if not backup_record:
            msg = f"Backup not found: {backup_id}"
            raise FileNotFoundError(msg)

        backup_dir = Path(backup_record.remote_path)
        if not backup_dir.exists():
            msg = f"Backup directory not found: {backup_dir}"
            raise FileNotFoundError(msg)

        # Load manifest
        manifest = BackupManifest.from_file(backup_dir / "metadata.json")

        # Verify checksums
        if not self._verify_checksums(backup_dir, manifest.checksums):
            msg = "Backup integrity check failed: checksum mismatch"
            raise RuntimeError(msg)

        # Determine target app name
        app_name = target_app_name or manifest.app_name

        # Get or create app
        app_repo = AppRepository(session=self.db_session)
        app = app_repo.get_one_or_none(name=app_name)

        if not app:
            # Create new app
            app = App(name=app_name)
            self.db_session.add(app)
            self.db_session.commit()
            app.create()  # Create directories

        # Stop app if running
        if app.is_running:
            log(f"Stopping app {app_name} for restore")
            # TODO: Call app.stop() when implemented

        try:
            # Restore components
            self._restore_source(app, backup_dir)
            self._restore_data(app, backup_dir)
            self._restore_env(app, backup_dir, manifest)
            self._restore_addons(app, backup_dir, manifest)

            # Restore app metadata
            app.hostname = manifest.app_metadata.get("hostname", "")
            app.port = manifest.app_metadata.get("port", 0)

            self.db_session.commit()

            log(f"Restore completed: {backup_id} -> {app_name}")

        except Exception as e:
            msg = f"Restore failed: {e}"
            raise RuntimeError(msg) from e

    def list_backups(
        self, app_name: str | None = None, limit: int = 20
    ) -> list[BackupManifest]:
        """List available backups.

        Args:
            app_name: Optional filter by application name
            limit: Maximum number of backups to return

        Returns:
            List of BackupManifest objects
        """
        query = self.db_session.query(Backup).join(App)

        if app_name:
            query = query.filter(App.name == app_name)

        query = query.order_by(Backup.created_at.desc()).limit(limit)

        backups = query.all()

        manifests = []
        for backup in backups:
            backup_dir = Path(backup.remote_path)
            manifest_file = backup_dir / "metadata.json"

            if manifest_file.exists():
                try:
                    manifest = BackupManifest.from_file(manifest_file)
                    manifests.append(manifest)
                except Exception as e:
                    log(f"Error loading manifest for {backup.remote_path}: {e}")

        return manifests

    def get_backup_info(self, backup_id: str) -> BackupManifest:
        """Get detailed backup information.

        Args:
            backup_id: Backup identifier

        Returns:
            BackupManifest with full details

        Raises:
            FileNotFoundError: If backup not found
        """
        backup_record = (
            self.db_session
            .query(Backup)
            .filter(Backup.remote_path.contains(backup_id))
            .first()
        )

        if not backup_record:
            msg = f"Backup not found: {backup_id}"
            raise FileNotFoundError(msg)

        backup_dir = Path(backup_record.remote_path)
        manifest_file = backup_dir / "metadata.json"

        if not manifest_file.exists():
            msg = f"Backup manifest not found: {manifest_file}"
            raise FileNotFoundError(msg)

        return BackupManifest.from_file(manifest_file)

    def delete_backup(self, backup_id: str) -> None:
        """Delete a backup.

        Args:
            backup_id: Backup to delete

        Raises:
            FileNotFoundError: If backup not found
        """
        backup_record = (
            self.db_session
            .query(Backup)
            .filter(Backup.remote_path.contains(backup_id))
            .first()
        )

        if not backup_record:
            msg = f"Backup not found: {backup_id}"
            raise FileNotFoundError(msg)

        backup_dir = Path(backup_record.remote_path)

        # Remove directory
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

        # Remove database record
        self.db_session.delete(backup_record)
        self.db_session.commit()

        log(f"Backup deleted: {backup_id}")

    def verify_backup(self, backup_id: str) -> dict[str, bool]:
        """Verify backup integrity by checking checksums.

        Args:
            backup_id: Backup to verify

        Returns:
            Dictionary mapping filenames to verification status

        Raises:
            FileNotFoundError: If backup not found
        """
        manifest = self.get_backup_info(backup_id)

        backup_record = (
            self.db_session
            .query(Backup)
            .filter(Backup.remote_path.contains(backup_id))
            .first()
        )

        if not backup_record:
            msg = f"Backup not found: {backup_id}"
            raise FileNotFoundError(msg)

        backup_dir = Path(backup_record.remote_path)

        results = {}
        for filename, expected_checksum in manifest.checksums.items():
            file_path = backup_dir / filename
            if file_path.exists():
                actual_checksum = self._calculate_checksum(file_path)
                results[filename] = actual_checksum == expected_checksum
            else:
                results[filename] = False

        return results

    # Private methods

    def _backup_source(self, app: App, backup_dir: Path) -> dict:
        """Backup git repository.

        Args:
            app: Application to backup
            backup_dir: Directory to store backup

        Returns:
            Dictionary with backup info
        """
        repo_path = app.repo_path
        if not repo_path.exists():
            log(f"Warning: Repository path does not exist: {repo_path}")
            return {"size": 0}

        tar_path = backup_dir / "source.tar.gz"

        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(repo_path, arcname="git")

        size = tar_path.stat().st_size
        log(f"Backed up source: {format_size(size)}")

        return {"size": size}

    def _backup_data(self, app: App, backup_dir: Path) -> dict:
        """Backup data directory.

        Args:
            app: Application to backup
            backup_dir: Directory to store backup

        Returns:
            Dictionary with backup info
        """
        data_path = app.data_path
        if not data_path.exists() or not any(data_path.iterdir()):
            log("Warning: Data directory is empty or does not exist")
            # Create empty tar
            tar_path = backup_dir / "data.tar.gz"
            with tarfile.open(tar_path, "w:gz") as tar:
                pass  # Empty tar
            return {"size": 0}

        tar_path = backup_dir / "data.tar.gz"

        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(data_path, arcname="data")

        size = tar_path.stat().st_size
        log(f"Backed up data: {format_size(size)}")

        return {"size": size}

    def _backup_env(self, app: App, backup_dir: Path) -> dict:
        """Backup environment variables.

        Args:
            app: Application to backup
            backup_dir: Directory to store backup

        Returns:
            Dictionary with backup info
        """
        env_data = {}
        for env_var in app.env_vars:
            env_data[env_var.name] = env_var.value

        env_path = backup_dir / "env.json"
        with Path(env_path).open("w") as f:
            json.dump(env_data, f, indent=2)

        # Set restrictive permissions for sensitive data
        env_path.chmod(0o600)

        size = env_path.stat().st_size
        log(f"Backed up {len(env_data)} environment variables")

        return {"size": size, "count": len(env_data)}

    def _backup_addons(self, app: App, backup_dir: Path) -> list[dict]:
        """Backup attached addons.

        Args:
            app: Application to backup
            backup_dir: Directory to store backup

        Returns:
            List of addon backup info dicts
        """
        addons_dir = backup_dir / "addons"
        addons_dir.mkdir(exist_ok=True)

        addons_info = []
        failed_addons = []

        # Discover attached services by examining environment variables
        attached_addons = self._get_attached_addons(app)

        for service_type, addon_name in attached_addons:
            try:
                addon = get_addon(service_type, addon_name)
                addon_backup_path = addon.backup()

                # Copy service backup to our backup directory
                dest_filename = f"{service_type}_{addon_name}{addon_backup_path.suffix}"
                dest_path = addons_dir / dest_filename

                shutil.copy2(addon_backup_path, dest_path)

                size = dest_path.stat().st_size
                log(
                    f"Backed up service {addon_name} ({service_type}): {format_size(size)}"
                )

                addons_info.append({
                    "type": service_type,
                    "name": addon_name,
                    "backup_file": f"addons/{dest_filename}",
                    "size_bytes": size,
                })

            except Exception as e:
                failed_addons.append((addon_name, service_type, str(e)))
                log(f"✗ Failed to backup service {addon_name} ({service_type}): {e}")

        # If any services failed to backup, raise an error
        if failed_addons:
            error_details = "\n".join(
                f"  - {name} ({stype}): {error}" for name, stype, error in failed_addons
            )
            msg = f"Backup failed: Could not backup {len(failed_addons)} attached service(s):\n{error_details}"
            raise RuntimeError(msg)

        return addons_info

    def _restore_source(self, app: App, backup_dir: Path) -> None:
        """Restore source code from backup.

        Args:
            app: Application to restore to
            backup_dir: Backup directory
        """
        tar_path = backup_dir / "source.tar.gz"
        if not tar_path.exists():
            log("Warning: No source backup found")
            return

        # Remove existing repository
        if app.repo_path.exists():
            shutil.rmtree(app.repo_path)

        # Extract tar (with filter for security)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(app.app_path, filter="data")

        log("Restored source code")

    def _restore_data(self, app: App, backup_dir: Path) -> None:
        """Restore data directory from backup.

        Args:
            app: Application to restore to
            backup_dir: Backup directory
        """
        tar_path = backup_dir / "data.tar.gz"
        if not tar_path.exists():
            log("Warning: No data backup found")
            return

        # Remove existing data
        if app.data_path.exists():
            shutil.rmtree(app.data_path)

        # Extract tar (with filter for security)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(app.app_path, filter="data")

        log("Restored data directory")

    def _restore_env(
        self, app: App, backup_dir: Path, manifest: BackupManifest
    ) -> None:
        """Restore environment variables from backup.

        Args:
            app: Application to restore to
            backup_dir: Backup directory
            manifest: Backup manifest
        """
        env_path = backup_dir / "env.json"
        if not env_path.exists():
            log("Warning: No environment backup found")
            return

        with Path(env_path).open() as f:
            env_data = json.load(f)

        # Clear existing env vars
        app.env_vars.clear()

        # Restore env vars
        for key, value in env_data.items():
            env_var = EnvVar(name=key, value=value, app=app)
            app.env_vars.append(env_var)

        log(f"Restored {len(env_data)} environment variables")

    def _restore_addons(
        self, app: App, backup_dir: Path, manifest: BackupManifest
    ) -> None:
        """Restore addons from backup.

        Args:
            app: Application to restore to
            backup_dir: Backup directory
            manifest: Backup manifest
        """
        for service_info in manifest.addons:
            service_type = service_info["type"]
            addon_name = service_info["name"]
            backup_file = backup_dir / service_info["backup_file"]

            if not backup_file.exists():
                log(f"Warning: Addon backup not found: {backup_file}")
                continue

            try:
                # Get or create service
                addon = get_addon(service_type, addon_name)

                # Restore service
                addon.restore(backup_file)

                log(f"Restored service {addon_name} ({service_type})")

            except Exception as e:
                log(f"Warning: Failed to restore service {addon_name}: {e}")

    def _get_attached_addons(self, app: App) -> list[tuple[str, str]]:
        """Get list of attached addons for an app.

        This examines environment variables to discover attached addons.

        Args:
            app: Application to check

        Returns:
            List of (service_type, addon_name) tuples
        """
        services = []

        # Look for DATABASE_URL (PostgreSQL)
        for env_var in app.env_vars:
            if env_var.name == "DATABASE_URL":
                # Extract database name from URL
                # postgresql://user:pass@localhost/dbname
                url = env_var.value
                if "postgresql://" in url:
                    db_name = url.split("/")[-1].split("?")[0]
                    # Addon name is typically the database name
                    services.append(("postgres", db_name))

            # TODO: Add detection for Redis, MySQL, etc.

        return services

    def _generate_backup_id(self) -> str:
        """Generate unique backup ID.

        Returns:
            Backup ID in format: YYYYMMDD_HHMMSS_<random>
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        random_suffix = secrets.token_hex(3)  # 6 characters
        return f"{timestamp}_{random_suffix}"

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file.

        Args:
            file_path: Path to file

        Returns:
            Hex string of SHA256 checksum
        """
        sha256 = hashlib.sha256()
        with Path(file_path).open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"

    def _verify_checksums(self, backup_dir: Path, checksums: dict[str, str]) -> bool:
        """Verify all checksums in a backup.

        Args:
            backup_dir: Backup directory
            checksums: Dictionary of filename -> checksum

        Returns:
            True if all checksums match
        """
        for filename, expected_checksum in checksums.items():
            file_path = backup_dir / filename
            if not file_path.exists():
                log(f"Error: Missing file: {filename}")
                return False

            actual_checksum = self._calculate_checksum(file_path)
            if actual_checksum != expected_checksum:
                log(f"Error: Checksum mismatch for {filename}")
                return False

        return True

    def _get_backup_dir(self, app_name: str, backup_id: str) -> Path:
        """Get the backup directory path for an app and backup ID.

        Args:
            app_name: Application name
            backup_id: Backup identifier

        Returns:
            Path to backup directory
        """
        return HopConfig.get_instance().BACKUP_ROOT / "apps" / app_name / backup_id

    def _get_hop3_version(self) -> str:
        """Get the current Hop3 version.

        Returns:
            Version string
        """
        return importlib.metadata.version("hop3-server")
