# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import contextlib
import io
import os
import shutil
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


def _get_int_limit(env_var: str, default: int) -> int:
    """Get an integer limit from environment variable."""
    value = os.environ.get(env_var, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# Security limits for archive extraction (configurable via environment)
# HOP3_MAX_ARCHIVE_SIZE:    Maximum compressed archive size (default: 1 GB)
# HOP3_MAX_EXTRACTED_SIZE:  Maximum uncompressed size; decompression-bomb
#                           protection (default: 5 GB)
# HOP3_MAX_ARCHIVE_MEMBERS: Maximum number of entries (default: 50 000)
DEFAULT_MAX_ARCHIVE_SIZE = 1024 * 1024 * 1024  # 1 GB
DEFAULT_MAX_EXTRACTED_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB
DEFAULT_MAX_ARCHIVE_MEMBERS = 50_000

# Chunk size for streaming extraction.
_COPY_CHUNK = 64 * 1024


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


def _validate_member(member: tarfile.TarInfo, target_dir: Path) -> None:
    """Per-member security gate.

    Raises on:
    - Malicious filenames (NUL, CR, LF).
    - Path traversal out of ``target_dir``.
    - Symlinks, hardlinks, devices, FIFOs, any non-file/non-dir type.

    The previous implementation relied on ``tarfile.data_filter`` (Python
    3.12+) or a legacy fallback. Rejecting unsafe types explicitly here
    avoids the version split and lets us add sharper error messages.
    """
    name = member.name
    if any(ch in name for ch in ("\0", "\r", "\n")):
        msg = (
            f"Malicious filename detected: {name!r} contains a NUL or "
            f"newline character."
        )
        raise ValueError(msg)

    # Symlinks and hardlinks escape the sandbox and can be used to
    # overwrite files outside the target dir (linkname is attacker-
    # controlled). Reject unconditionally.
    if member.issym() or member.islnk():
        msg = (
            f"Archive contains a {'symlink' if member.issym() else 'hardlink'} "
            f"entry {name!r}; refused."
        )
        raise ValueError(msg)

    # Block device/char-device/FIFO entries. Only regular files and
    # directories are allowed downstream.
    if not (member.isfile() or member.isdir()):
        msg = (
            f"Archive entry {name!r} has unsupported type "
            f"{member.type!r}; only files and directories are allowed."
        )
        raise ValueError(msg)

    # Path-traversal check: the resolved target must stay under the
    # destination. Uses str-comparison on resolved paths so a member
    # named "../x" doesn't escape even through symlinked parents.
    member_path = (target_dir / name).resolve()
    if target_dir not in member_path.parents and member_path != target_dir:
        msg = (
            f"Attempted path traversal in archive: {name!r} is outside "
            f"the target directory."
        )
        raise tarfile.TarError(msg)


def _extract_stream(
    tar: tarfile.TarFile,
    target_dir: Path,
    max_extracted: int,
    max_members: int,
) -> None:
    """Stream-extract ``tar`` into ``target_dir``.

    Iterates entries one at a time, validates each, writes regular files
    through a byte-counting copy, and aborts as soon as either:

    - the running uncompressed-byte total exceeds ``max_extracted``
      (decompression-bomb guard that doesn't trust the tar header), or
    - the number of entries exceeds ``max_members`` (inode-table DoS
      guard that doesn't trust the archive's member list length).

    On abort the partial extraction is removed by the caller via the
    prepare/clear-on-enter contract in ``extract_archive_to_dir``.
    """
    total_bytes = 0
    member_count = 0

    for member in tar:
        member_count += 1
        if member_count > max_members:
            msg = (
                f"Archive has more than {max_members} entries; "
                f"refused as a potential inode-table DoS. Set "
                f"HOP3_MAX_ARCHIVE_MEMBERS to adjust the limit."
            )
            raise ValueError(msg)

        _validate_member(member, target_dir)

        dest = target_dir / member.name

        if member.isdir():
            dest.mkdir(parents=True, exist_ok=True)
            continue

        # Regular file: stream through a byte-counting copy so we
        # catch decompression bombs even when the tar header lies
        # about size. tarfile.extractfile() returns a lazy reader that
        # decompresses on demand.
        dest.parent.mkdir(parents=True, exist_ok=True)
        source = tar.extractfile(member)
        if source is None:  # pragma: no cover - defensive, shouldn't hit
            continue
        with source, dest.open("wb") as out:
            while True:
                chunk = source.read(_COPY_CHUNK)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_extracted:
                    limit_mb = max_extracted / (1024 * 1024)
                    msg = (
                        f"Extraction exceeded {limit_mb:.0f} MB before "
                        f"the archive was exhausted; decompression-bomb "
                        f"guard triggered. Set HOP3_MAX_EXTRACTED_SIZE "
                        f"to adjust the limit."
                    )
                    raise ValueError(msg)
                out.write(chunk)

        # Preserve the file mode bits from the header, masked to the
        # owner's r/w/x + no-suid/sgid/sticky (safety).
        safe_mode = member.mode & 0o700
        with contextlib.suppress(PermissionError):  # pragma: no cover - defensive
            os.chmod(dest, safe_mode)


def extract_archive_to_dir(archive_bytes: bytes, target_dir: Path) -> None:
    """Extract an in-memory ``.tar.gz`` archive into ``target_dir``.

    Clears the target directory first so extraction starts clean, then
    streams each entry through a validator + byte-counting copy.

    Security measures:

    - Compressed-size cap (``HOP3_MAX_ARCHIVE_SIZE``, default 1 GB).
    - Real extracted-size cap (``HOP3_MAX_EXTRACTED_SIZE``, default 5 GB).
      The old pre-scan trusted the tar header's member sizes; this one
      measures actual bytes written and aborts mid-stream.
    - Member-count cap (``HOP3_MAX_ARCHIVE_MEMBERS``, default 50 000) to
      block inode-table DoS from archives full of zero-byte files.
    - Path-traversal rejection ("tar slip").
    - Unconditional rejection of symlinks, hardlinks, devices, and
      FIFOs. Only files and directories are materialised.
    - NUL / CR / LF rejection in filenames.

    Args:
        archive_bytes: The content of the .tar.gz archive as bytes.
        target_dir: The destination directory. Created if missing.

    Raises:
        ValueError: If the archive violates any size, count, or content
            constraint, or if a filename is malicious.
        tarfile.TarError: Path-traversal or read errors.
        PermissionError: If the target directory cannot be written.
    """
    _validate_archive_size(archive_bytes)
    target_dir = Path(target_dir).resolve()
    _prepare_target_directory(target_dir)

    max_extracted = _get_size_limit(
        "HOP3_MAX_EXTRACTED_SIZE", DEFAULT_MAX_EXTRACTED_SIZE
    )
    max_members = _get_int_limit(
        "HOP3_MAX_ARCHIVE_MEMBERS", DEFAULT_MAX_ARCHIVE_MEMBERS
    )

    fileobj = io.BytesIO(archive_bytes)

    try:
        with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
            try:
                _extract_stream(tar, target_dir, max_extracted, max_members)
            except BaseException:
                # Any failure leaves a partial tree. Nuke it so the
                # caller doesn't see a half-extracted sandbox.
                shutil.rmtree(target_dir, ignore_errors=True)
                target_dir.mkdir(parents=True, exist_ok=True)
                raise
    except tarfile.ReadError as e:
        msg = f"The provided bytes do not form a valid tar.gz archive: {e}"
        raise tarfile.ReadError(msg) from e
