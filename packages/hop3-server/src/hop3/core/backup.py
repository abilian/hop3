# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Backup and restore functionality for Hop3 applications.

This module provides the BackupManager class for creating and restoring
complete application backups including source code, data, environment
variables, and attached addons.
"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import importlib.metadata
import json
import os
import secrets
import shutil
import tarfile
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hop3.config import HopConfig
from hop3.core.plugins import get_addon
from hop3.lib import log
from hop3.orm import App, AppStateEnum, Backup, BackupStateEnum, EnvVar

# Runtime imports for Dishka DI (not just type hints)
from hop3.orm.repositories import (  # ruff:ignore[typing-only-first-party-import]
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
)

# Permission constants for backup directories and files.
# Backups contain plaintext env.json and DB dumps (ADR 024 phase 1 --- at-rest
# encryption is tracked for 0.6). Until then, the minimum viable mitigation is
# to keep the entire tree owner-only so one compromised app running as the
# shared `hop3` user cannot read another app's dumps. Individual backup files
# already default to 0o600 where written; the tree itself must be 0o700 so
# traversal is blocked too.
_BACKUP_DIR_MODE = 0o700


def _ensure_secure_backup_dir(path: Path) -> None:
    """
    Create ``path`` (and any missing ancestors up to BACKUP_ROOT) with
    owner-only permissions.

    ``Path.mkdir(mode=..., parents=True)`` only applies the mode to the
    leaf; intermediate directories inherit the process umask. We want
    the whole chain rooted at BACKUP_ROOT to be 0o700, so we walk
    upwards after creation and fix any ancestor whose mode is looser.

    SECURITY: pass ``mode=0o700`` to ``mkdir`` for the leaf so the brief
    window between dir creation and the chmod walk doesn't leave the
    leaf at umask perms (typically 0o755). The walk still has to widen
    its scope to ancestors, but the leaf — the directory we just made
    that holds the dumps — is tight from creation.

    Idempotent: safe to call on an already-existing tree.
    """
    path.mkdir(parents=True, exist_ok=True, mode=_BACKUP_DIR_MODE)
    # Walk back up to BACKUP_ROOT, tightening every ancestor whose mode
    # is looser than 0o700. Stop at BACKUP_ROOT itself (we control it
    # and don't want to climb past it).
    backup_root = HopConfig.get_instance().BACKUP_ROOT.resolve()
    current = path.resolve()
    try:
        current.relative_to(backup_root)
    except ValueError:
        # Path isn't under BACKUP_ROOT (test shim or misconfiguration);
        # still chmod the leaf, skip the walk.
        _chmod_if_looser(path, _BACKUP_DIR_MODE)
        return
    while True:
        _chmod_if_looser(current, _BACKUP_DIR_MODE)
        if current == backup_root:
            break
        parent = current.parent
        if parent == current:  # pragma: no cover - filesystem root guard
            break
        current = parent


def _chmod_if_looser(path: Path, target_mode: int) -> None:
    """
    chmod ``path`` to ``target_mode`` if its current mode is looser.

    Avoids unnecessary syscalls on already-tight trees and tolerates
    EPERM gracefully (the hop3 user owns its backup tree, so EPERM
    shouldn't happen, but we don't want to abort a backup if it does).
    """
    try:
        current_mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        return
    if current_mode == target_mode:
        return
    with contextlib.suppress(PermissionError):
        os.chmod(path, target_mode)


def format_size(size_bytes: float) -> str:
    """
    Format byte size as human-readable string.

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


def _strip_arc_root(arcname: str, root: str) -> str:
    """Path of a tar member relative to its archive root (``src``/``data``)."""
    name = arcname.rstrip("/")
    if name == root:
        return ""
    prefix = root + "/"
    return name.removeprefix(prefix)


def _matches_exclude(rel: str, patterns: list[str]) -> bool:
    """
    True if ``rel`` matches any ``[backup].exclude`` glob.

    A pattern matches the full relative path (``cache/*``), the basename
    (``*.tmp``), or any single path segment (``node_modules``), so common
    forms all work without the user thinking about anchoring.
    """
    if not rel:
        return False
    base = os.path.basename(rel)
    segments = [s for s in rel.split("/") if s]
    for pat in patterns:
        p = pat.rstrip("/")
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(base, p):
            return True
        if any(fnmatch.fnmatch(seg, p) for seg in segments):
            return True
    return False


def _is_under(path: Path, root: Path) -> bool:
    """True if ``path`` is ``root`` or below it (both already normalised)."""
    p, r = str(path), str(root)
    return p == r or p.startswith(r + os.sep)


@dataclass
class BackupManifest:
    """
    Represents a backup's metadata.

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
    # Persistent volumes archived in this backup (ADR 046 §2). Each entry has
    # {name, backup_file}. Defaulted so backups taken before volumes existed
    # still load.
    volumes: list[dict[str, Any]] = field(default_factory=list)
    # Extra app-relative directories archived from [backup].paths (into
    # extra.tar.gz, arcnames relative to app_path). Defaulted for old backups.
    extra_paths: list[str] = field(default_factory=list)
    # Live backup state (BackupStateEnum name), stamped from the DB record when
    # listing. A manifest only exists once a backup completes, so the persisted
    # default reflects that; the listing overrides it with the current DB state.
    state: str = "COMPLETED"

    @classmethod
    def from_json(cls, data: dict) -> BackupManifest:
        """
        Load manifest from JSON data.

        Args:
            data: Dictionary loaded from JSON

        Returns:
            BackupManifest instance
        """
        return cls(**data)

    def to_json(self) -> dict:
        """
        Convert manifest to JSON-serializable dict.

        Returns:
            Dictionary that can be serialized to JSON
        """
        return asdict(self)

    @classmethod
    def from_file(cls, path: Path) -> BackupManifest:
        """
        Load manifest from a JSON file.

        Args:
            path: Path to metadata.json file

        Returns:
            BackupManifest instance
        """
        with path.open() as f:
            data = json.load(f)
        return cls.from_json(data)

    def to_file(self, path: Path) -> None:
        """
        Write manifest to a JSON file.

        Args:
            path: Path where to write metadata.json
        """
        with path.open("w") as f:
            json.dump(self.to_json(), f, indent=2)


class BackupManager:
    """
    Manages backup and restore operations for applications.

    This class handles creating full backups of applications including:
    - Source code (git repository)
    - Application data directory
    - Environment variables
    - Attached addons (databases, caches, etc.)

    All backups are stored in /var/hop3/backups/apps/<app-name>/<backup-id>/
    """

    def __init__(
        self,
        backup_repo: BackupRepository,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
    ):
        """
        Initialize the backup manager.

        Args:
            backup_repo: Repository for backup operations
            app_repo: Repository for app operations
            addon_credential_repo: Repository for addon credential operations
        """
        self.backup_repo = backup_repo
        self.app_repo = app_repo
        self.addon_credential_repo = addon_credential_repo

    def create_backup(
        self, app: App, *, include_addons: bool = True
    ) -> tuple[str, Path]:
        """
        Create a backup of an application.

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

        # Create backup directory tree with restricted perms (0o700).
        _ensure_secure_backup_dir(backup_dir)

        # Create database record
        backup_record = Backup(
            app_id=app.id,
            state=BackupStateEnum.STARTED,
            format="tgz",
            remote_path=str(backup_dir),
            size=0,
            expires_after=0,
        )
        self.backup_repo.add(backup_record, auto_commit=True)

        try:
            # Backup components. The helpers create source.tar.gz / data.tar.gz
            # / env.json in backup_dir; the per-component metadata they return
            # is redundant with the directory scan below (which computes
            # checksums + total_size from the actual files), so we discard it.
            self._backup_source(app, backup_dir)
            self._backup_data(app, backup_dir)
            self._backup_env(app, backup_dir)
            # Persistent volumes (ADR 046 §2) are a sibling of src/ and data/,
            # so they must be archived explicitly or their data is silently
            # missing from the backup.
            volumes_info = self._backup_volumes(app, backup_dir)
            # Extra app-relative directories declared in [backup].paths.
            extra_info = self._backup_extra_paths(app, backup_dir)

            addons_info = []
            if include_addons:
                addons_info = self._backup_addons(app, backup_dir)

            # Create checksums
            checksums = {}
            for filename in ["source.tar.gz", "data.tar.gz", "env.json"]:
                file_path = backup_dir / filename
                if file_path.exists():
                    checksums[filename] = self._calculate_checksum(file_path)

            extra_entries = [extra_info] if extra_info else []
            for entry in [*addons_info, *volumes_info, *extra_entries]:
                entry_file = backup_dir / entry["backup_file"]
                if entry_file.exists():
                    checksums[entry["backup_file"]] = self._calculate_checksum(
                        entry_file
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
                volumes=volumes_info,
                extra_paths=extra_info["paths"] if extra_info else [],
            )

            # Write manifest
            manifest.to_file(backup_dir / "metadata.json")

            # Update database record
            backup_record.state = BackupStateEnum.COMPLETED
            backup_record.size = total_size
            self.backup_repo.update(backup_record, auto_commit=True)

            log(f"Backup created successfully: {backup_id}")

            return backup_id, backup_dir

        except Exception as e:
            # Mark as failed and clean up
            backup_record.state = BackupStateEnum.FAILED
            self.backup_repo.update(backup_record, auto_commit=True)

            # Try to remove partial backup
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

            msg = f"Backup creation failed: {e}"
            raise RuntimeError(msg) from e

    def register_existing_backup(self, backup_dir: Path) -> str:
        """
        Register a previously-created backup directory in the database.

        Used for cross-instance migration: an operator copies a backup
        tree (`<BACKUP_ROOT>/apps/<app>/<id>/`) from server A to server B
        and runs `hop3 backup register <path>` on B. This reads the
        manifest, ensures an app row exists for the manifest's app name,
        and inserts a Backup row pointing at the directory — so that
        `hop3 backup restore <id>` finds the backup the same way it
        would for a backup created locally.

        Idempotent: if a Backup row already exists for the given
        directory, returns the existing backup_id without modification.

        Args:
            backup_dir: absolute path to the backup directory; must
                contain ``metadata.json``.

        Returns:
            The backup_id (read from the manifest).

        Raises:
            FileNotFoundError: if the directory or its manifest is missing.
            ValueError: if the manifest's checksums don't validate.
        """
        if not backup_dir.exists() or not backup_dir.is_dir():
            msg = f"Backup directory not found: {backup_dir}"
            raise FileNotFoundError(msg)

        manifest_path = backup_dir / "metadata.json"
        if not manifest_path.exists():
            msg = f"Manifest not found in backup dir: {manifest_path}"
            raise FileNotFoundError(msg)

        manifest = BackupManifest.from_file(manifest_path)

        # Verify integrity before registering — refusing to register a
        # corrupt backup is friendlier than letting `restore` fail later.
        if not self._verify_checksums(backup_dir, manifest.checksums):
            msg = "Backup integrity check failed: checksum mismatch"
            raise ValueError(msg)

        # Idempotency: if we already have a row for this directory,
        # return the existing backup_id.
        existing = self.backup_repo.get_by_backup_id(manifest.backup_id)
        if existing and Path(existing.remote_path) == backup_dir:
            return manifest.backup_id

        # Ensure an app row exists for the manifest's app_name. The
        # actual restore step will repopulate the app's source/data; we
        # just need the FK target. Create as a placeholder if missing.
        app = self.app_repo.get_by_name(manifest.app_name)
        if not app:
            app = App(name=manifest.app_name)
            self.app_repo.add(app, auto_commit=True)

        backup_record = Backup(
            app_id=app.id,
            state=BackupStateEnum.COMPLETED,
            format="tgz",  # matches create_backup's hardcoding
            remote_path=str(backup_dir),
            size=manifest.size_bytes,
            expires_after=manifest.expires_after,
        )
        self.backup_repo.add(backup_record, auto_commit=True)

        return manifest.backup_id

    def restore_backup(
        self, backup_id: str, target_app_name: str | None = None
    ) -> None:
        """
        Restore an application from backup.

        Args:
            backup_id: ID of backup to restore
            target_app_name: Optional different app name to restore to

        Raises:
            RuntimeError: If restore fails
            FileNotFoundError: If backup not found
        """
        # Find backup in database
        backup_record = self.backup_repo.get_by_backup_id_with_app(backup_id)

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
        app = self.app_repo.get_by_name(app_name)

        if not app:
            # Create new app
            app = App(name=app_name)
            self.app_repo.add(app, auto_commit=True)
            app.create(setup_git=True)  # Create directories and set up git

        # Quiesce a running/failed instance before overwriting its files, so the
        # restore doesn't race live workers holding the source/data we replace.
        # app.stop() reaps and confirms (a no-op only when already stopped).
        if app.run_state != AppStateEnum.STOPPED:
            log(f"Stopping app {app_name} before restore")
            app.stop()

        try:
            # Restore components
            self._restore_source(app, backup_dir)
            # Extra [backup].paths overlay the restored source (they were
            # archived with arcnames relative to app_path).
            self._restore_extra(app, backup_dir, manifest)
            self._restore_data(app, backup_dir)
            # Volumes must be repopulated BEFORE app.deploy() re-links them:
            # realize_volumes only seeds an *empty* volume, so restored data
            # already on disk is preserved and simply re-linked (ADR 046 §2).
            self._restore_volumes(app, backup_dir, manifest)
            self._restore_env(app, backup_dir, manifest)
            self._restore_addons(app, backup_dir, manifest)

            # Restore app metadata
            app.hostname = manifest.app_metadata.get("hostname", "")
            app.port = manifest.app_metadata.get("port", 0)

            self.app_repo.update(app, auto_commit=True)

            # Build and spawn the app from the restored source. Without
            # this, restore only repopulates files on disk — the
            # operator would have to manually rebuild (`hop3 app
            # restart` only re-spawns existing workers; it doesn't
            # rebuild). For cross-instance migration in particular,
            # the destination has no prior build state, so spawn alone
            # is insufficient. "Restore" should mean the app is
            # running again, equivalent to its pre-backup state.
            app.deploy()

            log(f"Restore completed: {backup_id} -> {app_name}")

        except Exception as e:
            msg = f"Restore failed: {e}"
            raise RuntimeError(msg) from e

    def list_backups(
        self, app_name: str | None = None, limit: int = 20
    ) -> list[BackupManifest]:
        """
        List available backups.

        Args:
            app_name: Optional filter by application name
            limit: Maximum number of backups to return

        Returns:
            List of BackupManifest objects
        """
        backups = self.backup_repo.list_by_app_name(app_name, limit)

        manifests = []
        for backup in backups:
            backup_dir = Path(backup.remote_path)
            manifest_file = backup_dir / "metadata.json"

            if manifest_file.exists():
                try:
                    manifest = BackupManifest.from_file(manifest_file)
                    # Stamp the live DB state so the listing shows the real
                    # status instead of assuming every backup is COMPLETED.
                    manifests.append(replace(manifest, state=backup.state.name))
                except Exception as e:
                    log(f"Error loading manifest for {backup.remote_path}: {e}")

        return manifests

    def get_backup_info(self, backup_id: str) -> BackupManifest:
        """
        Get detailed backup information.

        Args:
            backup_id: Backup identifier

        Returns:
            BackupManifest with full details

        Raises:
            FileNotFoundError: If backup not found
        """
        backup_record = self.backup_repo.get_by_backup_id(backup_id)

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
        """
        Delete a backup.

        Args:
            backup_id: Backup to delete

        Raises:
            FileNotFoundError: If backup not found
        """
        backup_record = self.backup_repo.get_by_backup_id(backup_id)

        if not backup_record:
            msg = f"Backup not found: {backup_id}"
            raise FileNotFoundError(msg)

        backup_dir = Path(backup_record.remote_path)

        # Remove directory
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

        # Remove database record
        self.backup_repo.delete(backup_record.id, auto_commit=True)

        log(f"Backup deleted: {backup_id}")

    def verify_backup(self, backup_id: str) -> dict[str, bool]:
        """
        Verify backup integrity by checking checksums.

        Args:
            backup_id: Backup to verify

        Returns:
            Dictionary mapping filenames to verification status

        Raises:
            FileNotFoundError: If backup not found
        """
        manifest = self.get_backup_info(backup_id)

        backup_record = self.backup_repo.get_by_backup_id(backup_id)

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
        """
        Backup the deployed source tree (and the bare git repo if any).

        Hop3 has two deploy paths: git-push (populates ``app.repo_path``;
        the post-receive hook checks out to ``app.src_path``) and the
        tarball API (writes directly to ``app.src_path``, leaving
        ``app.repo_path`` empty). The original implementation tarred
        only the bare repo, which captured nothing useful for tarball
        deploys. We now archive both — ``app.src_path`` under
        ``arcname=src`` (the canonical "what's deployed") and the bare
        repo under ``arcname=git`` (so git-push history survives).

        Args:
            app: Application to backup
            backup_dir: Directory to store backup

        Returns:
            Dictionary with backup info
        """
        src_path = app.src_path
        repo_path = app.repo_path

        if not src_path.exists() and not repo_path.exists():
            log(f"Warning: Neither src nor repo exists for {app.name}")
            return {"size": 0}

        tar_path = backup_dir / "source.tar.gz"

        # Volume targets are realized as symlinks into src/ pointing OUTSIDE the
        # tree (ADR 046 §2). Archiving them would (a) store no real data and
        # (b) abort restore with AbsoluteLinkError under tar's data filter. Skip
        # them here — their bytes are archived separately by _backup_volumes.
        volume_arcnames = {
            "src/" + v["target"].strip("/") for v in self._app_volumes(app)
        }
        exclude = self._app_backup_config(app)["exclude"]

        def _src_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
            name = tarinfo.name.rstrip("/")
            # Volume targets are symlinks out of the tree — archived separately.
            if name in volume_arcnames:
                return None
            # [backup].exclude patterns prune members of the source tree.
            if exclude and _matches_exclude(_strip_arc_root(name, "src"), exclude):
                return None
            return tarinfo

        with tarfile.open(tar_path, "w:gz") as tar:
            if src_path.exists():
                tar.add(src_path, arcname="src", filter=_src_filter)
            if repo_path.exists():
                tar.add(repo_path, arcname="git")

        size = tar_path.stat().st_size
        log(f"Backed up source: {format_size(size)}")

        return {"size": size}

    def _app_volumes(self, app: App) -> list[dict]:
        """
        Declared [[volumes]] for an app, read from its deployed hop3.toml.

        Returns [] when the app has no hop3.toml or declares no volumes (the
        loader yields an empty config in that case, it does not raise). A
        hop3.toml that exists but is malformed propagates the parse error: the
        backup must fail loud rather than silently omit volume data while
        reporting success (the caller marks the backup FAILED and surfaces it).
        """
        from hop3.project.config import (  # ruff:ignore[import-outside-top-level]
            AppConfig,
        )

        # from_dir expects the app dir (its src_dir is <app_dir>/src), matching
        # how the deployer reads the config.
        return AppConfig.from_dir(app.app_path).hop3_config.volumes

    def _backup_volumes(self, app: App, backup_dir: Path) -> list[dict]:
        """
        Archive each persistent volume as its own member (ADR 046 §2).

        Each volume's real bytes live at ``app.volumes_path / <name>`` (outside
        src/ and data/), so it gets a dedicated ``volume-<name>.tar.gz``. A
        ``[volumes.backup] include = false`` opts a volume out.
        """
        results: list[dict] = []
        for vol in self._app_volumes(app):
            name = vol["name"]
            backup_cfg = vol.get("backup") or {}
            if backup_cfg.get("include") is False:
                log(f"Skipping volume '{name}' (backup.include = false)")
                continue

            vol_dir = app.volumes_path / name
            backup_file = f"volume-{name}.tar.gz"
            tar_path = backup_dir / backup_file
            with tarfile.open(tar_path, "w:gz") as tar:
                if vol_dir.exists():
                    tar.add(vol_dir, arcname=name)
            results.append({"name": name, "backup_file": backup_file})
            log(f"Backed up volume '{name}': {format_size(tar_path.stat().st_size)}")
        return results

    def _app_backup_config(self, app: App) -> dict:
        """
        The app's ``[backup]`` section: ``{"paths": [...], "exclude": [...]}``.

        Read from the deployed hop3.toml, like ``_app_volumes``. Empty lists
        when the app has no ``[backup]`` section.
        """
        from hop3.project.config import (  # ruff:ignore[import-outside-top-level]
            AppConfig,
        )

        return AppConfig.from_dir(app.app_path).hop3_config.backup

    def _backup_extra_paths(self, app: App, backup_dir: Path) -> dict | None:
        """
        Archive the directories declared in ``[backup].paths`` (additive).

        Each entry is resolved relative to the app's source dir and confined to
        the app tree (an entry that escapes it is a config error and fails the
        backup loudly — never a silent skip). A declared dir that doesn't exist
        yet is skipped with a warning. Archived into ``extra.tar.gz`` with
        arcnames relative to ``app_path``, so restore puts them back in place.
        Returns ``{"backup_file", "paths"}`` or None when nothing was archived.

        The confinement check uses ``realpath`` (not a lexical normpath), so a
        path that traverses an in-tree symlink pointing outside the app tree is
        rejected — a backup can only ever read data inside the app's subtree.
        """
        paths = self._app_backup_config(app)["paths"]
        if not paths:
            return None

        # realpath both sides: resolves symlinks so the "stays in the app tree"
        # check can't be defeated by an in-tree symlink to an external target.
        app_root = Path(os.path.realpath(app.app_path))
        archived: list[str] = []
        tar_path = backup_dir / "extra.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            for rel in paths:
                real = Path(os.path.realpath(app.src_path / rel))
                if os.path.isabs(rel) or not _is_under(real, app_root):
                    msg = (
                        f"[backup].paths entry {rel!r} escapes the app tree "
                        f"({app_root}); a backup can only read inside the app"
                    )
                    raise RuntimeError(msg)
                if not real.exists():
                    log(f"Skipping [backup].paths entry {rel!r}: does not exist")
                    continue
                arcname = os.path.relpath(real, app_root)
                tar.add(real, arcname=arcname)
                archived.append(arcname)

        if not archived:
            tar_path.unlink(missing_ok=True)
            return None
        log(
            f"Backed up {len(archived)} extra path(s): {format_size(tar_path.stat().st_size)}"
        )
        return {"backup_file": "extra.tar.gz", "paths": archived}

    def _backup_data(self, app: App, backup_dir: Path) -> dict:
        """
        Backup data directory.

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
        exclude = self._app_backup_config(app)["exclude"]

        def _data_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
            if exclude and _matches_exclude(
                _strip_arc_root(tarinfo.name.rstrip("/"), "data"), exclude
            ):
                return None
            return tarinfo

        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(data_path, arcname="data", filter=_data_filter)

        size = tar_path.stat().st_size
        log(f"Backed up data: {format_size(size)}")

        return {"size": size}

    def _backup_env(self, app: App, backup_dir: Path) -> dict:
        """
        Backup environment variables.

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
        """
        Backup attached addons.

        Args:
            app: Application to backup
            backup_dir: Directory to store backup

        Returns:
            List of addon backup info dicts
        """
        addons_dir = backup_dir / "addons"
        _ensure_secure_backup_dir(addons_dir)

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
        """
        Restore source tree (and bare git repo) from backup.

        Per the new ``_backup_source`` layout: the archive contains
        ``src/`` (the canonical deployed source) and may also contain
        ``git/`` (the bare repo, present iff git-push was used).
        Older backups (taken before this change) contain only ``git/``;
        we fall back to cloning ``git/`` → ``src/`` for those, so old
        backups remain restorable.

        Args:
            app: Application to restore to
            backup_dir: Backup directory
        """
        import subprocess  # ruff:ignore[import-outside-top-level]

        tar_path = backup_dir / "source.tar.gz"
        if not tar_path.exists():
            log("Warning: No source backup found")
            return

        # Clear any existing source state for a clean restore.
        if app.src_path.exists():
            shutil.rmtree(app.src_path)
        if app.repo_path.exists():
            shutil.rmtree(app.repo_path)

        # Extract tar (with filter for security)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(app.app_path, filter="data")

        # Backwards compat: backups taken before src/ was archived have
        # only git/. Recreate src/ by cloning from the bare repo.
        if not app.src_path.exists() and app.repo_path.exists():
            app.src_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--quiet",
                    str(app.repo_path),
                    str(app.src_path),
                ],
                check=True,
                capture_output=True,
            )

        log("Restored source code")

    def _restore_extra(
        self, app: App, backup_dir: Path, manifest: BackupManifest
    ) -> None:
        """
        Restore extra [backup].paths from ``extra.tar.gz`` into the app tree.

        Arcnames are relative to ``app_path``, so extracting there puts each
        directory back where it was. A manifest that records extra paths but is
        missing the archive is a corrupt/incomplete backup → fail loud (never
        report success while silently dropping data).
        """
        extra_paths = getattr(manifest, "extra_paths", None) or []
        if not extra_paths:
            return
        tar_path = backup_dir / "extra.tar.gz"
        if not tar_path.exists():
            msg = (
                f"Restore can't recover extra paths: extra.tar.gz missing in "
                f"{backup_dir} (backup is incomplete)"
            )
            raise RuntimeError(msg)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(app.app_path, filter="data")
        log(f"Restored {len(extra_paths)} extra path(s)")

    def _restore_data(self, app: App, backup_dir: Path) -> None:
        """
        Restore data directory from backup.

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

    def _restore_volumes(
        self, app: App, backup_dir: Path, manifest: BackupManifest
    ) -> None:
        """
        Restore persistent volumes from their per-volume archives (ADR 046 §2).

        Extracts each ``volume-<name>.tar.gz`` back into ``app.volumes_path /
        <name>`` so that the subsequent ``app.deploy()`` re-links it with the
        data intact.
        """
        volumes = getattr(manifest, "volumes", None) or []
        if not volumes:
            return

        volumes_root = app.volumes_path
        for vol in volumes:
            name = vol["name"]
            tar_path = backup_dir / vol["backup_file"]
            if not tar_path.exists():
                # The manifest recorded this volume as backed up, so a missing
                # archive means the backup is incomplete. Continuing would let
                # the later app.deploy() re-seed the volume EMPTY and still
                # report the restore as succeeded — silent data loss. Abort.
                msg = (
                    f"Restore can't recover volume {name!r}: its archive "
                    f"{vol['backup_file']!r} is missing from the backup, so the "
                    "backup is incomplete. Use an intact backup."
                )
                raise FileNotFoundError(msg)

            target_dir = volumes_root / name
            if target_dir.exists():
                shutil.rmtree(target_dir)
            volumes_root.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(volumes_root, filter="data")

        log("Restored volumes")

    def _restore_env(
        self, app: App, backup_dir: Path, manifest: BackupManifest
    ) -> None:
        """
        Restore environment variables from backup.

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
        """
        Restore addons from backup.

        Fails loud: a missing addon backup file, or a failed addon restore,
        aborts the whole restore. A silently-skipped addon would let a restore
        (and the rollback built on it) report success while an addon database was
        never restored — a rollback that lies about the state it returned to.

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
                msg = (
                    f"Addon backup file missing: {backup_file} "
                    f"({service_type}/{addon_name}) — the backup is incomplete."
                )
                raise RuntimeError(msg)

            addon = get_addon(service_type, addon_name)
            addon.restore(backup_file)
            log(f"Restored addon {addon_name} ({service_type})")

    def _get_attached_addons(self, app: App) -> list[tuple[str, str]]:
        """
        Get list of attached addons for an app.

        Queries AddonCredential records to find attached addons.

        Args:
            app: Application to check

        Returns:
            List of (service_type, addon_name) tuples
        """
        credentials = self.addon_credential_repo.get_by_app_id(app.id)

        return [(cred.addon_type, cred.addon_name) for cred in credentials]

    def _generate_backup_id(self) -> str:
        """
        Generate unique backup ID.

        Returns:
            Backup ID in format: YYYYMMDD_HHMMSS_<random>
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        random_suffix = secrets.token_hex(3)  # 6 characters
        return f"{timestamp}_{random_suffix}"

    def _calculate_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA256 checksum of a file.

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
        """
        Verify all checksums in a backup.

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
        """
        Get the backup directory path for an app and backup ID.

        Args:
            app_name: Application name
            backup_id: Backup identifier

        Returns:
            Path to backup directory
        """
        return HopConfig.get_instance().BACKUP_ROOT / "apps" / app_name / backup_id

    def _get_hop3_version(self) -> str:
        """
        Get the current Hop3 version.

        Returns:
            Version string
        """
        return importlib.metadata.version("hop3-server")
