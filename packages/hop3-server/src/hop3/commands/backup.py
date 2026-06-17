# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Commands for backing up and restoring applications."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from hop3.core.backup import BackupManager, format_size
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register

# Runtime imports for Dishka DI (not just type hints)
from hop3.orm.repositories import (  # noqa: TC001
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
)

from ._base import Command
from ._errors import command_context
from ._response import success, summary, table, text


@register
@dataclass(frozen=True)
class BackupCreateCmd(Command):
    """Create a backup of an application.

    Usage: hop3 backup create <app> [--no-addons]

    Examples:
        hop3 backup create my-app
        hop3 backup create my-app --no-addons
    """

    app_repo: AppRepository
    backup_repo: BackupRepository
    addon_credential_repo: AddonCredentialRepository
    name: ClassVar[tuple[str, ...]] = ("backup", "create")

    def call(self, *args):
        """Create a backup of an application."""
        if len(args) < 1:
            return [
                text(
                    "Usage: hop3 backup create <app> [--no-addons]\n\n"
                    "Example:\n"
                    "  hop3 backup create my-app"
                )
            ]

        app_name = args[0]
        include_addons = "--no-addons" not in args

        # Check if app exists
        app = self.app_repo.get_one_or_none(name=app_name)

        if not app:
            msg = f"App '{app_name}' not found"
            raise ValueError(msg)

        with command_context("creating backup", app_name=app_name):
            manager = BackupManager(
                backup_repo=self.backup_repo,
                app_repo=self.app_repo,
                addon_credential_repo=self.addon_credential_repo,
            )

            output = [text(f"Creating backup for app '{app_name}'...\n")]

            backup_id, backup_path = manager.create_backup(
                app, include_addons=include_addons
            )

            # Get backup info for display
            manifest = manager.get_backup_info(backup_id)

            output.append(success("Backup created successfully!\n"))

            info_lines = [
                f"Backup ID: {backup_id}",
                f"Location: {backup_path}",
                f"Total size: {format_size(manifest.size_bytes)}",
                "",
                "Contents:",
                "  - Source code",
                "  - Data directory",
                f"  - Environment variables ({manifest.env_vars_count} variables)",
            ]

            if manifest.addons:
                info_lines.append(f"  - Addons: {len(manifest.addons)}")
                for addon in manifest.addons:
                    info_lines.append(
                        f"    • {addon['name']} ({addon['type']}): "
                        f"{format_size(addon['size_bytes'])}"
                    )

            info_lines.extend([
                "",
                "To restore this backup:",
                f"  hop3 backup restore {backup_id}",
            ])

            output.append(text("\n".join(info_lines)))
            output.append(summary(f"created backup {backup_id} of {app_name}."))

        return output


@register
@dataclass(frozen=True)
class BackupListCmd(Command):
    """List all backups, optionally filtered by application.

    Usage: hop3 backup list [app] [--limit N]

    Examples:
        hop3 backup list
        hop3 backup list my-app
        hop3 backup list --limit 50
    """

    app_repo: AppRepository
    backup_repo: BackupRepository
    addon_credential_repo: AddonCredentialRepository
    name: ClassVar[tuple[str, ...]] = ("backup", "list")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app_name": {"positional": True},
        "limit": {"type": int, "default": 20},  # --limit N
    }

    def call(self, *args):
        """List available backups."""
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app_name")
        limit = parsed.get("limit", 20)

        with command_context("listing backups", app_name=app_name or "all"):
            manager = BackupManager(
                backup_repo=self.backup_repo,
                app_repo=self.app_repo,
                addon_credential_repo=self.addon_credential_repo,
            )
            backups = manager.list_backups(app_name, limit)

        if not backups:
            if app_name:
                return [text(f"No backups found for app '{app_name}'")]
            return [text("No backups found")]

        # Format as table
        headers = [
            "BACKUP ID",
            "APP",
            "SIZE",
            "CREATED",
            "STATUS",
            "SERVICES",
        ]

        rows = []
        for backup in backups:
            # Extract date from backup_id (YYYYMMDD_HHMMSS_random)
            backup_id_parts = backup.backup_id.split("_")
            if len(backup_id_parts) >= 2:
                date_str = backup_id_parts[0]
                time_str = backup_id_parts[1]
                created = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
            else:
                created = backup.created_at

            addons_list = [s["name"] for s in backup.addons]
            addons_str = ", ".join(addons_list) if addons_list else "-"

            rows.append([
                backup.backup_id,
                backup.app_name,
                format_size(backup.size_bytes),
                created,
                "COMPLETED",  # TODO: Get actual status from DB
                addons_str,
            ])

        return [table(headers=headers, rows=rows)]


@register
@dataclass(frozen=True)
class BackupInfoCmd(Command):
    """Show detailed information about a backup.

    Usage: hop3 backup show <backup-id>

    Examples:
        hop3 backup show 20251030_143022_a8f3d9
    """

    app_repo: AppRepository
    backup_repo: BackupRepository
    addon_credential_repo: AddonCredentialRepository
    name: ClassVar[tuple[str, ...]] = ("backup", "show")
    aliases: ClassVar[list[tuple[str, ...]]] = [("backup", "info")]

    def call(self, *args):
        """Get backup information."""
        if len(args) < 1:
            return [
                text(
                    "Usage: hop3 backup show <backup-id>\n\n"
                    "Example:\n"
                    "  hop3 backup show 20251030_143022_a8f3d9"
                )
            ]

        backup_id = args[0]

        with command_context("getting backup info", backup_id=backup_id):
            manager = BackupManager(
                backup_repo=self.backup_repo,
                app_repo=self.app_repo,
                addon_credential_repo=self.addon_credential_repo,
            )
            manifest = manager.get_backup_info(backup_id)

            # Verify backup integrity
            verification = manager.verify_backup(backup_id)
            all_valid = all(verification.values())

            lines = [
                "Backup Information",
                "=" * 50,
                "",
                f"Backup ID: {manifest.backup_id}",
                f"Application: {manifest.app_name}",
                f"Created: {manifest.created_at}",
                f"Total Size: {format_size(manifest.size_bytes)}",
                f"Format Version: {manifest.format_version}",
                f"Hop3 Version: {manifest.hop3_version}",
                "",
                "Contents:",
                f"  - Environment: {manifest.env_vars_count} variables",
            ]

            # Show checksums
            if manifest.checksums:
                lines.append("")
                lines.append("File Checksums:")
                for filename, checksum in manifest.checksums.items():
                    status = "✓" if verification.get(filename, False) else "✗"
                    lines.append(f"  {status} {filename}")
                    lines.append(f"     {checksum}")

            # Show services
            if manifest.addons:
                lines.append("")
                lines.append(f"Addons Included: ({len(manifest.addons)})")
                for addon in manifest.addons:
                    lines.append(
                        f"  - {addon['type']}:{addon['name']} "
                        f"({format_size(addon['size_bytes'])})"
                    )

            # Show app metadata
            if manifest.app_metadata:
                lines.append("")
                lines.append("Application State:")
                for key, value in manifest.app_metadata.items():
                    lines.append(f"  {key}: {value}")

            # Show integrity status
            lines.append("")
            if all_valid:
                lines.append("Integrity: ✓ All checksums valid")
            else:
                lines.append("Integrity: ✗ Some files failed checksum verification")

        return [text("\n".join(lines))]


@register
@dataclass(frozen=True)
class BackupRestoreCmd(Command):
    """Restore an application from a backup.

    Usage: hop3 backup restore <backup-id> [--target-app NAME]

    Examples:
        hop3 backup restore 20251030_143022_a8f3d9
        hop3 backup restore 20251030_143022_a8f3d9 --target-app new-app
    """

    app_repo: AppRepository
    backup_repo: BackupRepository
    addon_credential_repo: AddonCredentialRepository
    name: ClassVar[tuple[str, ...]] = ("backup", "restore")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "backup_id": {"positional": True},
        "target_app": {"type": str},  # --target-app NAME
    }

    def call(self, *args):
        """Restore an application from backup."""
        parsed = parse_cli_args(args, self._arg_spec)
        backup_id = parsed.get("backup_id")
        target_app_name = parsed.get("target_app")

        if not backup_id:
            return [
                text(
                    "Usage: hop3 backup restore <backup-id> [--target-app NAME]\n\n"
                    "Examples:\n"
                    "  hop3 backup restore 20251030_143022_a8f3d9\n"
                    "  hop3 backup restore 20251030_143022_a8f3d9 --target-app new-app"
                )
            ]

        with command_context("restoring backup", backup_id=backup_id):
            manager = BackupManager(
                backup_repo=self.backup_repo,
                app_repo=self.app_repo,
                addon_credential_repo=self.addon_credential_repo,
            )

            # Get backup info first
            manifest = manager.get_backup_info(backup_id)
            app_name = target_app_name or manifest.app_name

            output = [text(f"Restoring backup {backup_id}...\n")]

            # Verify backup integrity
            verification = manager.verify_backup(backup_id)
            all_valid = all(verification.values())

            if not all_valid:
                msg = "Backup integrity check failed: checksum mismatch"
                raise ValueError(msg)

            # Perform restore
            manager.restore_backup(backup_id, target_app_name)

            output.append(success("Restore completed successfully!\n"))

            info_lines = [
                f"Application: {app_name}",
                f"Hostname: {manifest.app_metadata.get('hostname', 'N/A')}",
                f"Port: {manifest.app_metadata.get('port', 'N/A')}",
                "",
                "To start the application:",
                f"  hop3 restart {app_name}",
            ]

            output.append(text("\n".join(info_lines)))
            output.append(summary(f"restored {app_name} from backup {backup_id}."))

        return output


@register
@dataclass(frozen=True)
class BackupRegisterCmd(Command):
    """Register a backup directory copied in from another Hop3 instance.

    Used during cross-instance migration: after copying a backup tree
    (`<BACKUP_ROOT>/apps/<app>/<id>/`) from server A to server B, run
    this on B to make the backup findable by `hop3 backup restore`.

    Reads the manifest, verifies checksums, ensures an app row exists
    for the original app name, and inserts a Backup row pointing at
    the directory. Idempotent: safe to re-run; existing rows are kept.

    Usage: hop3 backup register <backup-dir>

    Examples:
        hop3 backup register /home/hop3/backups/apps/myapp/20251030_143022_a8f3d9
    """

    app_repo: AppRepository
    backup_repo: BackupRepository
    addon_credential_repo: AddonCredentialRepository
    name: ClassVar[tuple[str, ...]] = ("backup", "register")
    _arg_spec: ClassVar[dict] = {
        "backup_dir": {"positional": True},
    }

    def call(self, *args):
        """Register an existing backup directory in the database."""
        parsed = parse_cli_args(args, self._arg_spec)
        backup_dir_str = parsed.get("backup_dir")

        if not backup_dir_str:
            return [
                text(
                    "Usage: hop3 backup register <backup-dir>\n\n"
                    "Example:\n"
                    "  hop3 backup register "
                    "/home/hop3/backups/apps/myapp/20251030_143022_a8f3d9"
                )
            ]

        backup_dir = Path(backup_dir_str).resolve()

        with command_context("registering backup", backup_dir=str(backup_dir)):
            manager = BackupManager(
                backup_repo=self.backup_repo,
                app_repo=self.app_repo,
                addon_credential_repo=self.addon_credential_repo,
            )

            backup_id = manager.register_existing_backup(backup_dir)

            return [
                success(f"Backup registered: {backup_id}\n"),
                text(
                    "Run `hop3 backup restore "
                    f"{backup_id}` to restore the app on this server."
                ),
                summary(f"registered backup {backup_id} from {backup_dir}."),
            ]


@register
@dataclass(frozen=True)
class BackupDestroyCmd(Command):
    """Delete a backup.

    WARNING: This action cannot be undone!

    Usage: hop3 backup destroy <backup-id>

    Examples:
        hop3 backup destroy 20251030_143022_a8f3d9
    """

    app_repo: AppRepository
    backup_repo: BackupRepository
    addon_credential_repo: AddonCredentialRepository
    name: ClassVar[tuple[str, ...]] = ("backup", "destroy")
    destructive: ClassVar[bool] = True

    def call(self, *args):
        """Delete a backup."""
        if len(args) < 1:
            return [
                text(
                    "Usage: hop3 backup destroy <backup-id>\n\n"
                    "WARNING: This action cannot be undone!\n\n"
                    "Example:\n"
                    "  hop3 backup destroy 20251030_143022_a8f3d9"
                )
            ]

        backup_id = args[0]

        with command_context("deleting backup", backup_id=backup_id):
            manager = BackupManager(
                backup_repo=self.backup_repo,
                app_repo=self.app_repo,
                addon_credential_repo=self.addon_credential_repo,
            )

            # Get backup info first
            manifest = manager.get_backup_info(backup_id)

            # In a real implementation, we would prompt for confirmation here
            # For now, we'll just show a warning
            output = [
                text(
                    f"Deleting backup {backup_id}\n\n"
                    f"Application: {manifest.app_name}\n"
                    f"Size: {format_size(manifest.size_bytes)}\n"
                    f"Created: {manifest.created_at}\n"
                )
            ]

            # Delete the backup
            manager.delete_backup(backup_id)

            output.append(success("Backup deleted successfully"))
            output.append(summary(f"destroyed backup {backup_id}."))

        return output


@register
@dataclass(frozen=True)
class BackupCmd(Command):
    """Manage application backups.

    Examples:
        hop3 backup create myapp       # Create a new backup
        hop3 backup list myapp         # List backups for myapp
        hop3 backup restore <id>       # Restore a backup
    """

    name: ClassVar[tuple[str, ...]] = ("backup",)
