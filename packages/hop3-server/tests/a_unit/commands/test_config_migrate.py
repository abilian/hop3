# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for config migration commands."""

from __future__ import annotations

from textwrap import dedent

import pytest

from hop3.commands.config import MigrateCmd
from hop3.project.procfile import Procfile

# Test cases: (procfile_content, expected_checks)
MIGRATION_TEST_CASES = [
    pytest.param(
        dedent("""
            web: gunicorn app:app --workers 4
            worker: celery worker -A tasks
        """),
        {
            "expected_sections": ["[metadata]", "[run]"],
            "expected_in_content": [
                'start = "gunicorn app:app --workers 4"',
                "# worker: celery worker -A tasks",
            ],
            "expected_not_in_content": ["[build]", "before-build"],
        },
        id="basic-web-and-worker",
    ),
    pytest.param(
        dedent("""
            prebuild: npm ci && npm run build
            prerun: npm run migrate
            web: node dist/server.js
            worker: node dist/worker.js
        """),
        {
            "expected_sections": ["[metadata]", "[build]", "[run]"],
            "expected_in_content": [
                'before-build = "npm ci && npm run build"',
                'start = "node dist/server.js"',
                'before-run = "npm run migrate"',
                "# worker: node dist/worker.js",
            ],
            "expected_not_in_content": [],
        },
        id="with-hooks",
    ),
    pytest.param(
        dedent("""
            prebuild: npm install
            postbuild: npm run build
            prerun: python manage.py migrate
            web: gunicorn app:app
            worker: celery worker
            beat: celery beat
        """),
        {
            "expected_sections": ["[metadata]", "[build]", "[run]"],
            "expected_in_content": [
                'before-build = "npm install"',
                'start = "gunicorn app:app"',
                'before-run = "python manage.py migrate"',
                "# worker: celery worker",
                "# beat: celery beat",
                "# Additional workers from Procfile",
            ],
            "expected_not_in_content": ["postbuild:"],
        },
        id="complex-with-multiple-workers",
    ),
    pytest.param(
        dedent("""
            web: python app.py
        """),
        {
            "expected_sections": ["[metadata]", "[run]"],
            "expected_in_content": ['start = "python app.py"'],
            "expected_not_in_content": ["[build]", "# worker:", "# Additional workers"],
        },
        id="simple-web-only",
    ),
    pytest.param(
        dedent("""
            prebuild: pip install -r requirements.txt
            prerun: python manage.py migrate
            web: gunicorn myapp.wsgi:application
        """),
        {
            "expected_sections": ["[metadata]", "[build]", "[run]"],
            "expected_in_content": [
                'before-build = "pip install -r requirements.txt"',
                'before-run = "python manage.py migrate"',
                'start = "gunicorn myapp.wsgi:application"',
            ],
            "expected_not_in_content": ["worker:", "beat:"],
        },
        id="django-typical",
    ),
    pytest.param(
        dedent("""
            web: npm start
            worker: npm run worker
            cron: npm run cron
        """),
        {
            "expected_sections": ["[metadata]", "[run]"],
            "expected_in_content": [
                'start = "npm start"',
                "# worker: npm run worker",
                "# cron: npm run cron",
            ],
            "expected_not_in_content": ["[build]"],
        },
        id="multiple-background-workers",
    ),
]


@pytest.mark.parametrize(("procfile_content", "expected"), MIGRATION_TEST_CASES)
def test_migrate_procfile_generation(tmp_path, procfile_content, expected):
    """Test Procfile to hop3.toml generation with various inputs."""
    # Create Procfile
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text(procfile_content)

    # Run migration
    cmd = MigrateCmd()
    result = cmd.call("procfile", str(tmp_path), dry_run=False, backup=False)

    # Check that hop3.toml was created
    hop3_toml = tmp_path / "hop3.toml"
    assert hop3_toml.exists(), "hop3.toml should be created"

    # Read generated content
    content = hop3_toml.read_text()

    # Check expected sections are present
    for section in expected["expected_sections"]:
        assert section in content, f"Expected section {section} not found"

    # Check expected strings are in content
    for expected_str in expected["expected_in_content"]:
        assert expected_str in content, f"Expected string '{expected_str}' not found"

    # Check strings that should NOT be in content
    for unexpected_str in expected["expected_not_in_content"]:
        assert unexpected_str not in content, (
            f"Unexpected string '{unexpected_str}' found"
        )

    # Check result messages
    assert result[0]["t"] == "success"


def test_migrate_procfile_dry_run(tmp_path):
    """Test dry-run mode (no files written)."""
    procfile_content = dedent("""
        web: python app.py
    """)
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text(procfile_content)

    cmd = MigrateCmd()
    result = cmd.call("procfile", str(tmp_path), dry_run=True, backup=False)

    # Check that NO files were created
    hop3_toml = tmp_path / "hop3.toml"
    assert not hop3_toml.exists()
    backup = tmp_path / "Procfile.bak"
    assert not backup.exists()

    # Check that result contains the generated content
    assert any("dry-run" in r.get("text", "") for r in result)
    assert any("[run]" in r.get("text", "") for r in result)


def test_migrate_procfile_with_backup(tmp_path):
    """Test migration with backup creation."""
    procfile_content = dedent("""
        web: python app.py
    """)
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text(procfile_content)

    cmd = MigrateCmd()
    cmd.call("procfile", str(tmp_path), dry_run=False, backup=True)

    # Check backup was created
    backup = tmp_path / "Procfile.bak"
    assert backup.exists()
    assert backup.read_text() == procfile_content

    # hop3.toml should also exist
    hop3_toml = tmp_path / "hop3.toml"
    assert hop3_toml.exists()


def test_migrate_procfile_no_backup(tmp_path):
    """Test migration without creating backup."""
    procfile_content = dedent("""
        web: python app.py
    """)
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text(procfile_content)

    cmd = MigrateCmd()
    cmd.call("procfile", str(tmp_path), dry_run=False, backup=False)

    # Backup should not exist
    backup = tmp_path / "Procfile.bak"
    assert not backup.exists()

    # But hop3.toml should exist
    hop3_toml = tmp_path / "hop3.toml"
    assert hop3_toml.exists()


def test_migrate_procfile_already_exists(tmp_path):
    """Test error when hop3.toml already exists."""
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text("web: python app.py")

    # Create existing hop3.toml
    hop3_toml = tmp_path / "hop3.toml"
    hop3_toml.write_text("[metadata]\nid = 'existing'")

    cmd = MigrateCmd()
    result = cmd.call("procfile", str(tmp_path), dry_run=False, backup=False)

    # Should return error
    assert result[0]["t"] == "error"
    assert "already exists" in result[0]["text"]


def test_migrate_procfile_not_found(tmp_path):
    """Test error when Procfile doesn't exist."""
    cmd = MigrateCmd()
    result = cmd.call("procfile", str(tmp_path), dry_run=False, backup=False)

    assert result[0]["t"] == "error"
    assert "not found" in result[0]["text"]


def test_migrate_procfile_directory_not_found(tmp_path):
    """Test error when directory doesn't exist."""
    nonexistent = tmp_path / "nonexistent"
    cmd = MigrateCmd()
    result = cmd.call("procfile", str(nonexistent), dry_run=False, backup=False)

    assert result[0]["t"] == "error"
    assert "Directory not found" in result[0]["text"]


def test_migrate_procfile_src_directory(tmp_path):
    """Test finding Procfile in src/ subdirectory."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    procfile_path = src_dir / "Procfile"
    procfile_path.write_text("web: gunicorn app:app")

    cmd = MigrateCmd()
    result = cmd.call("procfile", str(tmp_path), dry_run=False, backup=False)

    # Should find and convert the Procfile in src/
    hop3_toml = src_dir / "hop3.toml"
    assert hop3_toml.exists()
    assert result[0]["t"] == "success"


def test_migrate_procfile_hop3_subdirectory(tmp_path):
    """Test finding Procfile in src/hop3/ subdirectory."""
    hop3_dir = tmp_path / "src" / "hop3"
    hop3_dir.mkdir(parents=True)
    procfile_path = hop3_dir / "Procfile"
    procfile_path.write_text("web: python app.py")

    cmd = MigrateCmd()
    cmd.call("procfile", str(tmp_path), dry_run=False, backup=False)

    # Should find and convert the Procfile in src/hop3/
    hop3_toml = hop3_dir / "hop3.toml"
    assert hop3_toml.exists()


def test_generate_hop3_toml_direct():
    """Test _generate_hop3_toml method directly with Procfile object."""
    procfile_content = dedent("""
        prebuild: npm ci
        prerun: python manage.py migrate
        web: gunicorn app:app
        worker: celery worker
    """)

    procfile = Procfile.from_str(procfile_content)
    cmd = MigrateCmd()
    toml_content = cmd._generate_hop3_toml(procfile)

    # Check structure
    assert "[metadata]" in toml_content
    assert "[build]" in toml_content
    assert 'before-build = "npm ci"' in toml_content
    assert "[run]" in toml_content
    assert 'start = "gunicorn app:app"' in toml_content
    assert 'before-run = "python manage.py migrate"' in toml_content
    assert "# worker: celery worker" in toml_content
