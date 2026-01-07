# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Commands for backing up and restoring applications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.core.backup import BackupManager, format_size
from hop3.lib.decorators import register
from hop3.orm.repositories import AppRepository

from ._base import Command
from ._errors import command_context

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
@dataclass(frozen=True)
class BackupCreateCmd(Command):
    """Create a backup of an application.

    Usage: hop3 backup:create <app> [--no-addons]

    Examples:
        hop3 backup:create my-app
        hop3 backup:create my-app --no-addons
    """

    db_session: Session
    name: ClassVar[str] = "backup:create"

    def call(self, *args):
        """Create a backup of an application."""
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 backup:create <app> [--no-addons]\n\n"
                        "Example:\n"
                        "  hop3 backup:create my-app"
                    ),
                }
            ]

        app_name = args[0]
        include_addons = "--no-addons" not in args

        # Check if app exists
        app_repo = AppRepository(session=self.db_session)
        app = app_repo.get_one_or_none(name=app_name)

        if not app:
            msg = f"App '{app_name}' not found"
            raise ValueError(msg)

        with command_context("creating backup", app_name=app_name):
            manager = BackupManager(self.db_session)

            output = [
                {"t": "text", "text": f"Creating backup for app '{app_name}'...\n"}
            ]

            backup_id, backup_path = manager.create_backup(
                app, include_addons=include_addons
            )

            # Get backup info for display
            manifest = manager.get_backup_info(backup_id)

            output.append({
                "t": "success",
                "text": "Backup created successfully!\n",
            })

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
                f"  hop3 backup:restore {backup_id}",
            ])

            output.append({"t": "text", "text": "\n".join(info_lines)})

        return output


@register
@dataclass(frozen=True)
class BackupListCmd(Command):
    """List all backups, optionally filtered by application.

    Usage: hop3 backup:list [app] [--limit N]

    Examples:
        hop3 backup:list
        hop3 backup:list my-app
        hop3 backup:list --limit 50
    """

    db_session: Session
    name: ClassVar[str] = "backup:list"

    def call(self, *args):
        """List available backups."""
        app_name = None
        limit = 20

        # Parse arguments
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--limit" and i + 1 < len(args):
                try:
                    limit = int(args[i + 1])
                    i += 2
                except ValueError:
                    return [{"t": "error", "text": "Invalid limit value"}]
            elif not arg.startswith("--"):
                app_name = arg
                i += 1
            else:
                i += 1

        with command_context("listing backups", app_name=app_name or "all"):
            manager = BackupManager(self.db_session)
            backups = manager.list_backups(app_name, limit)

        if not backups:
            if app_name:
                return [{"t": "text", "text": f"No backups found for app '{app_name}'"}]
            return [{"t": "text", "text": "No backups found"}]

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

        return [{"t": "table", "headers": headers, "rows": rows}]


@register
@dataclass(frozen=True)
class BackupInfoCmd(Command):
    """Show detailed information about a backup.

    Usage: hop3 backup:info <backup-id>

    Examples:
        hop3 backup:info 20251030_143022_a8f3d9
    """

    db_session: Session
    name: ClassVar[str] = "backup:info"

    def call(self, *args):
        """Get backup information."""
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 backup:info <backup-id>\n\n"
                        "Example:\n"
                        "  hop3 backup:info 20251030_143022_a8f3d9"
                    ),
                }
            ]

        backup_id = args[0]

        with command_context("getting backup info", backup_id=backup_id):
            manager = BackupManager(self.db_session)
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

        return [{"t": "text", "text": "\n".join(lines)}]


@register
@dataclass(frozen=True)
class BackupRestoreCmd(Command):
    """Restore an application from a backup.

    Usage: hop3 backup:restore <backup-id> [--target-app NAME]

    Examples:
        hop3 backup:restore 20251030_143022_a8f3d9
        hop3 backup:restore 20251030_143022_a8f3d9 --target-app new-app
    """

    db_session: Session
    name: ClassVar[str] = "backup:restore"

    def call(self, *args):
        """Restore an application from backup."""
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 backup:restore <backup-id> [--target-app NAME]\n\n"
                        "Examples:\n"
                        "  hop3 backup:restore 20251030_143022_a8f3d9\n"
                        "  hop3 backup:restore 20251030_143022_a8f3d9 --target-app new-app"
                    ),
                }
            ]

        backup_id = args[0]
        target_app_name = None

        # Parse optional arguments
        i = 1
        while i < len(args):
            if args[i] == "--target-app" and i + 1 < len(args):
                target_app_name = args[i + 1]
                i += 2
            else:
                i += 1

        with command_context("restoring backup", backup_id=backup_id):
            manager = BackupManager(self.db_session)

            # Get backup info first
            manifest = manager.get_backup_info(backup_id)
            app_name = target_app_name or manifest.app_name

            output = [{"t": "text", "text": f"Restoring backup {backup_id}...\n"}]

            # Verify backup integrity
            verification = manager.verify_backup(backup_id)
            all_valid = all(verification.values())

            if not all_valid:
                msg = "Backup integrity check failed: checksum mismatch"
                raise ValueError(msg)

            # Perform restore
            manager.restore_backup(backup_id, target_app_name)

            output.append({
                "t": "success",
                "text": "Restore completed successfully!\n",
            })

            info_lines = [
                f"Application: {app_name}",
                f"Hostname: {manifest.app_metadata.get('hostname', 'N/A')}",
                f"Port: {manifest.app_metadata.get('port', 'N/A')}",
                "",
                "To start the application:",
                f"  hop3 restart {app_name}",
            ]

            output.append({"t": "text", "text": "\n".join(info_lines)})

        return output


@register
@dataclass(frozen=True)
class BackupDeleteCmd(Command):
    """Delete a backup.

    WARNING: This action cannot be undone!

    Usage: hop3 backup:delete <backup-id>

    Examples:
        hop3 backup:delete 20251030_143022_a8f3d9
    """

    db_session: Session
    name: ClassVar[str] = "backup:delete"
    destructive: ClassVar[bool] = True

    def call(self, *args):
        """Delete a backup."""
        if len(args) < 1:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 backup:delete <backup-id>\n\n"
                        "WARNING: This action cannot be undone!\n\n"
                        "Example:\n"
                        "  hop3 backup:delete 20251030_143022_a8f3d9"
                    ),
                }
            ]

        backup_id = args[0]

        with command_context("deleting backup", backup_id=backup_id):
            manager = BackupManager(self.db_session)

            # Get backup info first
            manifest = manager.get_backup_info(backup_id)

            # In a real implementation, we would prompt for confirmation here
            # For now, we'll just show a warning
            output = [
                {
                    "t": "text",
                    "text": (
                        f"Deleting backup {backup_id}\n\n"
                        f"Application: {manifest.app_name}\n"
                        f"Size: {format_size(manifest.size_bytes)}\n"
                        f"Created: {manifest.created_at}\n"
                    ),
                }
            ]

            # Delete the backup
            manager.delete_backup(backup_id)

            output.append({
                "t": "success",
                "text": "Backup deleted successfully",
            })

        return output


@register
@dataclass(frozen=True)
class BackupCmd(Command):
    """Manage application backups.

    Commands:
      backup:create   Create a backup of an application
      backup:list     List all backups
      backup:info     Show detailed backup information
      backup:restore  Restore an application from backup
      backup:delete   Delete a backup
    """

    name: ClassVar[str] = "backup"
