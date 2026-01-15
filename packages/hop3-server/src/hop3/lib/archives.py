# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import io
import shutil
import stat
import tarfile
import time
from pathlib import Path

# Security limits for archive extraction
MAX_ARCHIVE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
MAX_EXTRACTED_SIZE_BYTES = (
    2 * 1024 * 1024 * 1024
)  # 2 GB (decompression bomb protection)
MAX_FILE_COUNT = 10000  # Maximum number of files in archive

# Retry settings for robust deletion
RMTREE_MAX_RETRIES = 3
RMTREE_RETRY_DELAY = 0.1  # seconds


def _validate_archive_size(archive_bytes: bytes) -> None:
    """Validate that archive size doesn't exceed limits."""
    if len(archive_bytes) > MAX_ARCHIVE_SIZE_BYTES:
        msg = (
            f"Archive size ({len(archive_bytes)} bytes) exceeds maximum "
            f"allowed size ({MAX_ARCHIVE_SIZE_BYTES} bytes)"
        )
        raise ValueError(msg)


def _robust_rmtree(path: Path) -> None:
    """Remove a directory tree robustly, handling permission and race condition issues.

    This handles common issues with npm's node_modules and similar complex structures:
    - Read-only files (common in npm packages)
    - Race conditions when files are still being accessed
    - Deep nesting

    Args:
        path: Directory to remove

    Raises:
        OSError: If deletion fails after all retries
    """

    def handle_remove_readonly(func, path, exc_info):
        """Error handler that fixes read-only permissions and retries."""
        # If it's a permission error, try to fix permissions and retry
        if isinstance(exc_info[1], PermissionError):
            try:
                path.chmod(stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                func(path)
                return
            except OSError:
                pass
        # Re-raise the original exception
        raise exc_info[1]

    last_error = None
    for attempt in range(RMTREE_MAX_RETRIES):
        try:
            shutil.rmtree(path, onerror=handle_remove_readonly)
            return  # Success
        except OSError as e:
            last_error = e
            if attempt < RMTREE_MAX_RETRIES - 1:
                # Wait a bit before retrying (handles race conditions)
                time.sleep(RMTREE_RETRY_DELAY * (attempt + 1))
            continue

    # All retries failed - try one last time with ignore_errors as fallback
    shutil.rmtree(path, ignore_errors=True)

    # Check if it's really gone
    if path.exists():
        raise last_error or OSError(f"Failed to remove directory: {path}")


def _prepare_target_directory(target_dir: Path) -> None:
    """Clear or create the target directory.

    Uses robust deletion that handles:
    - Read-only files (common in npm packages)
    - Race conditions when processes are still accessing files
    - Complex nested structures
    """
    if target_dir.exists():
        # Clear the directory to ensure we start fresh.
        for item in target_dir.iterdir():
            if item.is_dir():
                _robust_rmtree(item)
            else:
                try:
                    item.unlink()
                except PermissionError:
                    # Try fixing permissions and retry
                    Path(item).chmod(stat.S_IRWXU)
                    item.unlink()
    else:
        # Create the directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)


def _validate_archive_members(members: list) -> None:
    """Validate archive member count and total size."""
    # File count limit
    if len(members) > MAX_FILE_COUNT:
        msg = (
            f"Archive contains {len(members)} files, which exceeds "
            f"the maximum allowed ({MAX_FILE_COUNT})"
        )
        raise ValueError(msg)

    # Decompression bomb protection
    total_size = sum(member.size for member in members if member.isfile())
    if total_size > MAX_EXTRACTED_SIZE_BYTES:
        msg = (
            f"Archive would extract to {total_size} bytes, which exceeds "
            f"the maximum allowed ({MAX_EXTRACTED_SIZE_BYTES})"
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
    - Archive size limits (500 MB)
    - Decompression bomb protection (max 2 GB extracted)
    - File count limits (max 10,000 files)
    - Malicious filename detection

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
