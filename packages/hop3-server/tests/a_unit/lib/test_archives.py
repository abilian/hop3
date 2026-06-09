# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Security tests for hop3.lib.archives.extract_archive_to_dir.

Wave 4 of the security remediation: cover the decompression bomb,
inode-table DoS, symlink/hardlink rejection, path traversal, and the
legitimate happy-path for files + directories.
"""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

import pytest

from hop3.lib.archives import extract_archive_to_dir

if TYPE_CHECKING:
    from collections.abc import Sequence


def _make_targz(members: Sequence[tuple[tarfile.TarInfo, bytes | None]]) -> bytes:
    """Build an in-memory tar.gz from a list of (TarInfo, payload?) tuples."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for info, payload in members:
            fileobj = io.BytesIO(payload) if payload is not None else None
            tar.addfile(info, fileobj)
    return buf.getvalue()


def _file_info(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = 0o644
    info.type = tarfile.REGTYPE
    return info


def _dir_info(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.mode = 0o755
    info.type = tarfile.DIRTYPE
    return info


def _symlink_info(name: str, target: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = target
    return info


def _hardlink_info(name: str, target: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.LNKTYPE
    info.linkname = target
    return info


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_extract_regular_file(tmp_path: Path) -> None:
    payload = b"hello world"
    archive = _make_targz([(_file_info("README.md", len(payload)), payload)])
    extract_archive_to_dir(archive, tmp_path)
    assert (tmp_path / "README.md").read_bytes() == payload


def test_extract_nested_dirs(tmp_path: Path) -> None:
    payload = b"x = 1"
    members = [
        (_dir_info("pkg/"), None),
        (_file_info("pkg/__init__.py", 0), b""),
        (_file_info("pkg/mod.py", len(payload)), payload),
    ]
    extract_archive_to_dir(_make_targz(members), tmp_path)
    assert (tmp_path / "pkg" / "mod.py").read_bytes() == payload


# ---------------------------------------------------------------------------
# Decompression bomb: header lies, actual payload is large
# ---------------------------------------------------------------------------


def test_bomb_with_lying_header_caught_by_real_byte_counter(
    tmp_path: Path, monkeypatch
) -> None:
    """The header claims 1 byte but the payload is larger than the cap.
    The real-byte streaming counter must abort mid-extract."""
    monkeypatch.setenv("HOP3_MAX_EXTRACTED_SIZE", "256")

    # Build the archive by hand: claim size=1 in the header but the
    # stream contains a full block of zeros.
    info = _file_info("fat.bin", 1)  # lying size
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # tarfile pads writes to 512-byte blocks; force it to write 2 KiB
        # of content by pretending the header claims a tiny size.
        info.size = 2048
        tar.addfile(info, io.BytesIO(b"A" * 2048))
    archive_bytes = buf.getvalue()

    with pytest.raises(ValueError, match="decompression-bomb"):
        extract_archive_to_dir(archive_bytes, tmp_path)


def test_bomb_leaves_no_partial_tree(tmp_path: Path, monkeypatch) -> None:
    """After aborting on a bomb, the target directory is clean."""
    monkeypatch.setenv("HOP3_MAX_EXTRACTED_SIZE", "256")
    payload = b"A" * 2048
    archive = _make_targz([(_file_info("fat.bin", len(payload)), payload)])
    with pytest.raises(ValueError):
        extract_archive_to_dir(archive, tmp_path)
    # Directory still exists but contains no partial files.
    assert tmp_path.exists()
    assert not any(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# Inode DoS: too many entries
# ---------------------------------------------------------------------------


def test_too_many_members_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOP3_MAX_ARCHIVE_MEMBERS", "5")
    members = [(_file_info(f"f{i}.txt", 0), b"") for i in range(10)]
    with pytest.raises(ValueError, match="more than 5 entries"):
        extract_archive_to_dir(_make_targz(members), tmp_path)


# ---------------------------------------------------------------------------
# Symlink / hardlink / special-type rejection
# ---------------------------------------------------------------------------


def test_symlink_rejected(tmp_path: Path) -> None:
    members = [(_symlink_info("link", "/etc/passwd"), None)]
    with pytest.raises(ValueError, match="symlink"):
        extract_archive_to_dir(_make_targz(members), tmp_path)


def test_hardlink_rejected(tmp_path: Path) -> None:
    members = [
        (_file_info("real.txt", 4), b"abcd"),
        (_hardlink_info("clone", "real.txt"), None),
    ]
    with pytest.raises(ValueError, match="hardlink"):
        extract_archive_to_dir(_make_targz(members), tmp_path)


def test_fifo_rejected(tmp_path: Path) -> None:
    info = tarfile.TarInfo("pipe")
    info.type = tarfile.FIFOTYPE
    with pytest.raises(ValueError, match="unsupported type"):
        extract_archive_to_dir(_make_targz([(info, None)]), tmp_path)


# ---------------------------------------------------------------------------
# Path traversal
# ---------------------------------------------------------------------------


def test_path_traversal_rejected(tmp_path: Path) -> None:
    payload = b"pwn"
    members = [(_file_info("../evil.txt", len(payload)), payload)]
    with pytest.raises(tarfile.TarError, match="path traversal"):
        extract_archive_to_dir(_make_targz(members), tmp_path)


def test_filename_with_newline_rejected(tmp_path: Path) -> None:
    info = _file_info("legit\nevil", 0)
    with pytest.raises(ValueError, match="NUL or newline"):
        extract_archive_to_dir(_make_targz([(info, b"")]), tmp_path)


# ---------------------------------------------------------------------------
# Compressed-size cap
# ---------------------------------------------------------------------------


def test_compressed_size_cap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOP3_MAX_ARCHIVE_SIZE", "100")
    # 10 KB of compressible data -> tiny gzip, but tack raw bytes on
    # the end so the buffer exceeds 100 bytes.
    archive = _make_targz([(_file_info("a.txt", 10), b"A" * 10)]) + b"\0" * 200
    with pytest.raises(ValueError, match="Archive size"):
        extract_archive_to_dir(archive, tmp_path)


def test_bad_gzip_raises_readerror(tmp_path: Path) -> None:
    with pytest.raises(tarfile.ReadError):
        extract_archive_to_dir(b"not a tar.gz", tmp_path)


def test_valid_gzip_but_not_tar_raises(tmp_path: Path) -> None:
    # Valid gzip stream, but not a tar archive.
    plain_gz = gzip.compress(b"hello world")
    with pytest.raises(tarfile.ReadError):
        extract_archive_to_dir(plain_gz, tmp_path)
