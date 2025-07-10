# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pathspec


def generate_archive(source_dir: Path) -> bytes:
    """
    Creates an in-memory tar.gz archive of a source directory as a bytes object,
    excluding files and directories specified in a .gitignore file.

    Args:
        source_dir (Path): The path to the directory to archive.

    Returns:
        bytes: The content of the .tar.gz archive as a bytes object.

    Raises:
        ValueError: If the source_dir is not a valid directory.
        FileNotFoundError: If the source_dir does not exist.
    """
    source_dir = Path(source_dir).resolve()

    if not source_dir.exists():
        msg = f"Source directory not found: {source_dir}"
        raise FileNotFoundError(msg)
    if not source_dir.is_dir():
        msg = f"Source path is not a directory: {source_dir}"
        raise ValueError(msg)

    # --- 1. Load .gitignore rules ---
    gitignore_path = source_dir / ".gitignore"
    spec: pathspec.PathSpec | None = None
    if gitignore_path.is_file():
        with open(gitignore_path, encoding="utf-8") as f:
            spec = pathspec.PathSpec.from_lines("gitwildmatch", f)

    # --- 2. Walk the directory and gather files to include ---
    files_to_add: list[Path] = []

    for file_path in source_dir.rglob("*"):
        # Get path relative to the source directory for matching
        relative_path = file_path.relative_to(source_dir)

        # Let pathspec determine if the file should be ignored
        if spec and spec.match_file(str(relative_path)):
            continue

        # We only add files to the tar, not directories
        if not file_path.is_file():
            continue

        files_to_add.append(file_path)

    # --- 3. Create the tar.gz archive in memory ---
    fileobj = io.BytesIO()

    # The 'w:gz' mode creates a gzip-compressed tar file.
    # We pass our BytesIO object as the file to write to.
    with tarfile.open(fileobj=fileobj, mode="w:gz") as tar:
        archive_root_name = source_dir.name

        for file_path in files_to_add:
            relative_path = file_path.relative_to(source_dir)
            arcname = Path(archive_root_name) / relative_path
            tar.add(file_path, arcname=str(arcname))

    return fileobj.getvalue()
