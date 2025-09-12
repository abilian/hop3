# Copyright (c) 2025, Abilian SAS
# test_generate_archive.py
from __future__ import annotations

import io
import tarfile
import tempfile
from pathlib import Path

from hop3_cli.arguments import generate_archive

GITIGNORE = """
# IDE and OS files
.idea/
*.swo
*.swp
.DS_Store

# Python virtual environment
venv/
__pycache__/

# Build artifacts
dist/
*.pyc

# Log files
*.log
!important.log

# A specific file to ignore
config.local.json
"""


def test_generate_archive():
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)

        (project_dir / ".gitignore").write_text(GITIGNORE)

        # Create files and directories that should be INCLUDED
        (project_dir / "src").mkdir()
        (project_dir / "src" / "main.py").write_text("print('hello world')")
        (project_dir / "README.md").write_text("# My Cool Project")
        (project_dir / "important.log").write_text(
            "This log is important and should be included."
        )

        # Create files and directories that should be EXCLUDED
        (project_dir / ".idea").mkdir()
        (project_dir / ".idea" / "workspace.xml").touch()
        (project_dir / "venv").mkdir()
        (project_dir / "venv" / "lib").mkdir()
        (project_dir / "src" / "main.pyc").touch()
        (project_dir / "debug.log").touch()
        (project_dir / "config.local.json").touch()

        archive_bytes = generate_archive(project_dir)
        assert isinstance(archive_bytes, bytes)

        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
            archived_files = tar.getnames()
            assert "src/main.py" in archived_files
            assert "README.md" in archived_files
            assert ".gitignore" in archived_files
            assert "important.log" in archived_files
            assert "venv/lib" not in archived_files
            assert "debug.log" not in archived_files
            assert "config.local.json" not in archived_files
