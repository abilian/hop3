# Copyright (c) 2025, Abilian SAS
# test_generate_archive.py
from __future__ import annotations

import io
import tarfile
import tempfile
from pathlib import Path

from hop3_cli.commands.arguments import generate_archive

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


def test_dockerignore_does_not_govern_the_deploy_source():
    """A `.dockerignore` must NOT decide what gets deployed.

    Frameworks like Quarkus ship a `.dockerignore` of `*` + a `target/`
    allowlist (for `docker build`). If the deploy honored it, pom.xml/src would
    be excluded and the server would see "no language toolchain". The deploy
    must fall through to `.gitignore` instead.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)

        # Quarkus-style .dockerignore: exclude everything but built artifacts.
        (project_dir / ".dockerignore").write_text(
            "*\n!target/*-runner\n!target/quarkus-app/*\n"
        )
        # A normal .gitignore that only excludes build output.
        (project_dir / ".gitignore").write_text("target/\n")

        (project_dir / "pom.xml").write_text("<project/>")
        (project_dir / "src").mkdir()
        (project_dir / "src" / "App.java").write_text("class App {}")
        (project_dir / "target").mkdir()
        (project_dir / "target" / "App.class").touch()

        archive_bytes = generate_archive(project_dir)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
            names = tar.getnames()
            assert "pom.xml" in names  # source survives (not gutted by dockerignore)
            assert "src/App.java" in names
            assert "target/App.class" not in names  # .gitignore still excludes target/
