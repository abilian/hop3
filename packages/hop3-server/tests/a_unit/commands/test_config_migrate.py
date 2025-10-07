# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for config migration commands."""

from __future__ import annotations

from hop3.commands.config import MigrateProcfileCmd


def test_migrate_procfile_basic(tmp_path):
    """Test basic Procfile to hop3.toml migration."""
    # Create a simple Procfile
    procfile_content = """web: gunicorn app:app --workers 4
worker: celery worker -A tasks
"""
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text(procfile_content)

    # Run migration
    cmd = MigrateProcfileCmd()
    result = cmd.call(str(tmp_path), dry_run=False, backup=True)

    # Check that hop3.toml was created
    hop3_toml = tmp_path / "hop3.toml"
    assert hop3_toml.exists()

    # Check backup was created
    backup = tmp_path / "Procfile.bak"
    assert backup.exists()
    assert backup.read_text() == procfile_content

    # Check hop3.toml content
    content = hop3_toml.read_text()
    assert "[metadata]" in content
    assert "[run]" in content
    assert 'start = "gunicorn app:app --workers 4"' in content
    assert "# worker: celery worker -A tasks" in content

    # Check result messages
    assert result[0]["t"] == "success"


def test_migrate_procfile_with_hooks(tmp_path):
    """Test migration with prebuild and prerun hooks."""
    procfile_content = """prebuild: npm install
prerun: python manage.py migrate
web: npm start
"""
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text(procfile_content)

    cmd = MigrateProcfileCmd()
    result = cmd.call(str(tmp_path), dry_run=False, backup=False)

    hop3_toml = tmp_path / "hop3.toml"
    content = hop3_toml.read_text()

    # Check that hooks were properly migrated
    assert "[build]" in content
    assert 'before-build = "npm install"' in content
    assert "[run]" in content
    assert 'start = "npm start"' in content
    assert 'before-run = "python manage.py migrate"' in content


def test_migrate_procfile_dry_run(tmp_path):
    """Test dry-run mode (no files written)."""
    procfile_content = "web: python app.py"
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text(procfile_content)

    cmd = MigrateProcfileCmd()
    result = cmd.call(str(tmp_path), dry_run=True, backup=False)

    # Check that NO files were created
    hop3_toml = tmp_path / "hop3.toml"
    assert not hop3_toml.exists()
    backup = tmp_path / "Procfile.bak"
    assert not backup.exists()

    # Check that result contains the generated content
    assert any("dry-run" in r.get("text", "") for r in result)
    assert any("[run]" in r.get("text", "") for r in result)


def test_migrate_procfile_already_exists(tmp_path):
    """Test error when hop3.toml already exists."""
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text("web: python app.py")

    # Create existing hop3.toml
    hop3_toml = tmp_path / "hop3.toml"
    hop3_toml.write_text("[metadata]\nid = 'existing'")

    cmd = MigrateProcfileCmd()
    result = cmd.call(str(tmp_path), dry_run=False, backup=False)

    # Should return error
    assert result[0]["t"] == "error"
    assert "already exists" in result[0]["text"]


def test_migrate_procfile_not_found(tmp_path):
    """Test error when Procfile doesn't exist."""
    cmd = MigrateProcfileCmd()
    result = cmd.call(str(tmp_path), dry_run=False, backup=False)

    assert result[0]["t"] == "error"
    assert "not found" in result[0]["text"]


def test_migrate_procfile_src_directory(tmp_path):
    """Test finding Procfile in src/ subdirectory."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    procfile_path = src_dir / "Procfile"
    procfile_path.write_text("web: gunicorn app:app")

    cmd = MigrateProcfileCmd()
    result = cmd.call(str(tmp_path), dry_run=False, backup=False)

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

    cmd = MigrateProcfileCmd()
    result = cmd.call(str(tmp_path), dry_run=False, backup=False)

    # Should find and convert the Procfile in src/hop3/
    hop3_toml = hop3_dir / "hop3.toml"
    assert hop3_toml.exists()


def test_migrate_procfile_no_backup(tmp_path):
    """Test migration without creating backup."""
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text("web: python app.py")

    cmd = MigrateProcfileCmd()
    result = cmd.call(str(tmp_path), dry_run=False, backup=False)

    # Backup should not exist
    backup = tmp_path / "Procfile.bak"
    assert not backup.exists()

    # But hop3.toml should exist
    hop3_toml = tmp_path / "hop3.toml"
    assert hop3_toml.exists()


def test_generate_hop3_toml_complex(tmp_path):
    """Test TOML generation with complex Procfile."""
    from hop3.project.procfile import Procfile

    procfile_content = """prebuild: npm ci
postbuild: npm run build
prerun: python manage.py migrate
web: gunicorn app:app
worker: celery worker
beat: celery beat
"""
    procfile_path = tmp_path / "Procfile"
    procfile_path.write_text(procfile_content)

    procfile = Procfile.from_file(procfile_path)
    cmd = MigrateProcfileCmd()
    toml_content = cmd._generate_hop3_toml(procfile)

    # Check structure
    assert "[metadata]" in toml_content
    assert "[build]" in toml_content
    assert 'before-build = "npm ci"' in toml_content
    assert "[run]" in toml_content
    assert 'start = "gunicorn app:app"' in toml_content
    assert 'before-run = "python manage.py migrate"' in toml_content

    # postbuild, worker, beat should be in comments
    assert "# worker: celery worker" in toml_content
    assert "# beat: celery beat" in toml_content
