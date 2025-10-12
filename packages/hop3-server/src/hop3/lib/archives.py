# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import io
import shutil
import tarfile
from pathlib import Path

# Security limits for archive extraction
MAX_ARCHIVE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
MAX_EXTRACTED_SIZE_BYTES = (
    2 * 1024 * 1024 * 1024
)  # 2 GB (decompression bomb protection)
MAX_FILE_COUNT = 10000  # Maximum number of files in archive


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
    # --- 0. Validate archive size ---
    if len(archive_bytes) > MAX_ARCHIVE_SIZE_BYTES:
        msg = (
            f"Archive size ({len(archive_bytes)} bytes) exceeds maximum "
            f"allowed size ({MAX_ARCHIVE_SIZE_BYTES} bytes)"
        )
        raise ValueError(msg)

    target_dir = Path(target_dir).resolve()

    # --- 1. Prepare the target directory ---
    if target_dir.exists():
        # Clear the directory to ensure we start fresh.
        # This is safer than deleting and recreating, which could have
        # permission issues if the parent directory is not writable.
        for item in target_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    else:
        # Create the directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)

    # --- 2. Extract the archive from the in-memory bytes object ---
    fileobj = io.BytesIO(archive_bytes)

    try:
        with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
            members = tar.getmembers()

            # --- Security Check: File count limit ---
            if len(members) > MAX_FILE_COUNT:
                msg = (
                    f"Archive contains {len(members)} files, which exceeds "
                    f"the maximum allowed ({MAX_FILE_COUNT})"
                )
                raise ValueError(msg)

            # --- Security Check: Decompression bomb protection ---
            total_size = sum(member.size for member in members if member.isfile())
            if total_size > MAX_EXTRACTED_SIZE_BYTES:
                msg = (
                    f"Archive would extract to {total_size} bytes, which exceeds "
                    f"the maximum allowed ({MAX_EXTRACTED_SIZE_BYTES})"
                )
                raise ValueError(msg)

            # Important: Use the `data` filter with Python 3.12+ for security.
            # For older versions, we manually check each member.
            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=target_dir, filter="data")
            else:
                for member in members:
                    # --- Security Check: Prevent Path Traversal ---
                    # Resolve the member path relative to target_dir, not cwd
                    member_path = (target_dir / member.name).resolve()
                    # A safe path must be a subdirectory of the target_dir.
                    # We achieve this by checking if target_dir is a parent or the path itself.
                    if (
                        target_dir not in member_path.parents
                        and member_path != target_dir
                    ):
                        msg = f"Attempted path traversal in tar file: '{member.name}' is outside the target directory."
                        raise tarfile.TarError(msg)

                    # --- Security Check: Malicious filenames ---
                    if any(char in member.name for char in ["\0", "\r", "\n"]):
                        msg = f"Malicious filename detected: '{member.name}' contains null or newline characters"
                        raise ValueError(msg)

                    tar.extract(member, path=target_dir)

        print(f"Successfully extracted archive to: {target_dir}")

    except tarfile.ReadError as e:
        print(f"Error: The provided bytes do not form a valid tar.gz archive. {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred during extraction: {e}")
        raise
