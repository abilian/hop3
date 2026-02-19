# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import io
import os
import stat
import tarfile
from pathlib import Path

from hop3.lib.util import robust_rmtree


def _get_size_limit(env_var: str, default: int) -> int:
    """Get a size limit from environment variable or use default.

    Supports suffixes: K, M, G (case-insensitive).
    Examples: "100M", "1G", "500000000"
    """
    value = os.environ.get(env_var, "").strip()
    if not value:
        return default

    try:
        # Check for suffix
        suffix = value[-1].upper()
        if suffix == "K":
            return int(value[:-1]) * 1024
        if suffix == "M":
            return int(value[:-1]) * 1024 * 1024
        if suffix == "G":
            return int(value[:-1]) * 1024 * 1024 * 1024
        return int(value)
    except (ValueError, IndexError):
        return default


# Security limits for archive extraction (configurable via environment)
# HOP3_MAX_ARCHIVE_SIZE: Maximum compressed archive size (default: 1 GB)
# HOP3_MAX_EXTRACTED_SIZE: Maximum extracted size / decompression bomb protection (default: 5 GB)
DEFAULT_MAX_ARCHIVE_SIZE = 1024 * 1024 * 1024  # 1 GB
DEFAULT_MAX_EXTRACTED_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB


def _validate_archive_size(archive_bytes: bytes) -> None:
    """Validate that archive size doesn't exceed limits.

    Limit is configurable via HOP3_MAX_ARCHIVE_SIZE environment variable.
    """
    max_size = _get_size_limit("HOP3_MAX_ARCHIVE_SIZE", DEFAULT_MAX_ARCHIVE_SIZE)
    if len(archive_bytes) > max_size:
        size_mb = len(archive_bytes) / (1024 * 1024)
        limit_mb = max_size / (1024 * 1024)
        msg = (
            f"Archive size ({size_mb:.1f} MB) exceeds maximum "
            f"allowed size ({limit_mb:.0f} MB). "
            f"Set HOP3_MAX_ARCHIVE_SIZE to increase the limit."
        )
        raise ValueError(msg)


def _prepare_target_directory(target_dir: Path) -> None:
    """Clear or create the target directory.

    Uses robust deletion that handles:
    - Read-only files (common in npm packages)
    - Race conditions when processes are still accessing files
    - Complex nested structures
    - Symbolic links (must be unlinked, not rmtree'd)
    """
    if target_dir.exists():
        # Clear the directory to ensure we start fresh.
        for item in target_dir.iterdir():
            # Handle symlinks first - is_dir() returns True for symlinks to directories
            # but shutil.rmtree fails on symlinks, so we must unlink them instead
            if item.is_symlink():
                item.unlink()
            elif item.is_dir():
                robust_rmtree(item)
            else:
                try:
                    item.unlink()
                except PermissionError:
                    # Try fixing permissions and retry
                    os.chmod(item, stat.S_IRWXU)
                    item.unlink()
    else:
        # Create the directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)


def _validate_archive_members(members: list) -> None:
    """Validate archive members for security.

    Checks for decompression bomb attacks by validating total extracted size.
    Limit is configurable via HOP3_MAX_EXTRACTED_SIZE environment variable.
    """
    max_extracted = _get_size_limit(
        "HOP3_MAX_EXTRACTED_SIZE", DEFAULT_MAX_EXTRACTED_SIZE
    )

    # Decompression bomb protection
    total_size = sum(member.size for member in members if member.isfile())
    if total_size > max_extracted:
        size_mb = total_size / (1024 * 1024)
        limit_mb = max_extracted / (1024 * 1024)
        msg = (
            f"Archive would extract to {size_mb:.1f} MB, which exceeds "
            f"the maximum allowed ({limit_mb:.0f} MB). "
            f"Set HOP3_MAX_EXTRACTED_SIZE to increase the limit."
        )
        raise ValueError(msg)


def _validate_member_path(member, target_dir: Path) -> None:
    """Validate a single archive member for security issues."""
    # Prevent path traversal
    member_path = (target_dir / member.name).resolve()
    if target_dir not in member_path.parents and member_path != target_dir:
        msg = f"Attempted path traversal in tar file: '{member.name}' is outside the target directory."
        raise tarfile.TarError(msg)

    # Check for malicious filenames
    if any(char in member.name for char in ["\0", "\r", "\n"]):
        msg = f"Malicious filename detected: '{member.name}' contains null or newline characters"
        raise ValueError(msg)


def _extract_members_legacy(
    tar: tarfile.TarFile, members: list, target_dir: Path
) -> None:
    """Extract tar members with legacy manual security checks (Python < 3.12)."""
    for member in members:
        _validate_member_path(member, target_dir)
        tar.extract(member, path=target_dir)


def extract_archive_to_dir(archive_bytes: bytes, target_dir: Path) -> None:
    """
    Extracts an in-memory tar.gz archive into a target directory.

    This function first clears the target directory (if it exists) before
    extraction to ensure it's a clean slate. It also prevents path traversal
    attacks ("tar slip") by ensuring all members are extracted safely within
    the target directory.

    Security measures:
    - Path traversal prevention (tar slip protection)
    - Archive size limits (configurable, default 1 GB)
    - Decompression bomb protection (configurable, default 5 GB extracted)
    - Malicious filename detection

    Environment variables for configuration:
    - HOP3_MAX_ARCHIVE_SIZE: Max compressed archive size (e.g., "1G", "500M")
    - HOP3_MAX_EXTRACTED_SIZE: Max extracted size (e.g., "5G", "2G")

    Args:
        archive_bytes (bytes): The content of the .tar.gz archive as a bytes object.
        target_dir (Path): The path to the directory where the archive will be
                           extracted. The directory will be created if it
                           doesn't exist.

    Raises:
        ValueError: If archive violates security constraints
        tarfile.ReadError: If the provided bytes are not a valid tar archive.
        PermissionError: If unable to clear or write to the target directory.
        Exception: Catches other potential extraction errors.
    """
    _validate_archive_size(archive_bytes)
    target_dir = Path(target_dir).resolve()
    _prepare_target_directory(target_dir)

    fileobj = io.BytesIO(archive_bytes)

    try:
        with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
            members = tar.getmembers()
            _validate_archive_members(members)

            # Use the `data` filter with Python 3.12+ for security.
            # For older versions, manually check each member.
            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=target_dir, filter="data")
            else:
                _extract_members_legacy(tar, members, target_dir)

    except tarfile.ReadError as e:
        msg = f"The provided bytes do not form a valid tar.gz archive: {e}"
        raise tarfile.ReadError(msg) from e
