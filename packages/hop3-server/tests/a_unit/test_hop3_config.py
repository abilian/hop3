# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for hop3.toml configuration parser."""

from __future__ import annotations

from hop3.project.hop3_config import Hop3Config


def test_from_str_basic():
    """Test parsing basic hop3.toml from string."""
    content = """
[metadata]
id = "my-app"
version = "1.0.0"
title = "My Application"

[build]
build = "npm run build"
before-build = "npm install"

[run]
start = "npm start"
"""
    config = Hop3Config.from_str(content)

    assert config.app_id == "my-app"
    assert config.version == "1.0.0"
    assert config.title == "My Application"
    assert config.build_commands == ["npm run build"]
    assert config.before_build_commands == ["npm install"]
    assert config.start_command == "npm start"


def test_from_file(tmp_path):
    """Test parsing hop3.toml from file."""
    hop3_toml = tmp_path / "hop3.toml"
    hop3_toml.write_text("""
[metadata]
id = "test-app"

[run]
start = "python app.py"
""")

    config = Hop3Config.from_file(hop3_toml)
    assert config.app_id == "test-app"
    assert config.start_command == "python app.py"
    assert config.config_path == hop3_toml


def test_build_section():
    """Test [build] section parsing."""
    content = """
[build]
build = ["make", "make install"]
before-build = "autogen.sh"
test = "make test"
packages = ["gcc", "make"]
pip-install = ["pytest", "mypy"]
"""
    config = Hop3Config.from_str(content)

    assert config.build_commands == ["make", "make install"]
    assert config.before_build_commands == ["autogen.sh"]
    assert config.test_commands == ["make test"]
    assert config.build_packages == ["gcc", "make"]
    assert config.pip_install == ["pytest", "mypy"]


def test_run_section():
    """Test [run] section parsing."""
    content = """
[run]
start = "gunicorn app:app"
before-run = ["python manage.py migrate", "python manage.py collectstatic --noinput"]
packages = ["postgresql", "redis"]
"""
    config = Hop3Config.from_str(content)

    assert config.start_command == "gunicorn app:app"
    assert config.before_run_commands == [
        "python manage.py migrate",
        "python manage.py collectstatic --noinput",
    ]
    assert config.run_packages == ["postgresql", "redis"]


def test_get_workers_from_run_section():
    """Test conversion of [run] section to Procfile-style workers."""
    content = """
[build]
before-build = "npm install"

[run]
start = "npm start"
before-run = "npm run migrate"
"""
    config = Hop3Config.from_str(content)
    workers = config.get_workers_from_run_section()

    assert workers == {
        "web": "npm start",
        "prerun": "npm run migrate",
        "prebuild": "npm install",
    }


def test_get_workers_with_list_commands():
    """Test worker extraction with list-format commands."""
    content = """
[run]
start = ["gunicorn app:app", "--workers 4"]
before-run = ["echo 'Starting'", "python setup.py"]
"""
    config = Hop3Config.from_str(content)
    workers = config.get_workers_from_run_section()

    # List commands should be joined with &&
    assert workers["web"] == "gunicorn app:app && --workers 4"
    assert workers["prerun"] == "echo 'Starting' && python setup.py"


def test_env_section():
    """Test [env] section parsing."""
    content = """
[env]
DEBUG = "false"
DATABASE_URL = "postgresql://localhost/mydb"
API_KEY = "secret-key"
"""
    config = Hop3Config.from_str(content)

    assert config.env["DEBUG"] == "false"
    assert config.env["DATABASE_URL"] == "postgresql://localhost/mydb"
    assert config.env["API_KEY"] == "secret-key"


def test_port_section():
    """Test [port] section parsing."""
    content = """
[port]
web = 8000
api = 8080
"""
    config = Hop3Config.from_str(content)

    assert config.port["web"] == 8000
    assert config.port["api"] == 8080


def test_providers_section():
    """Test [[provider]] section parsing."""
    content = """
[[provider]]
name = "postgres"
plan = "standard"

[[provider]]
name = "redis"
plan = "basic"
"""
    config = Hop3Config.from_str(content)

    assert len(config.providers) == 2
    assert config.providers[0]["name"] == "postgres"
    assert config.providers[0]["plan"] == "standard"
    assert config.providers[1]["name"] == "redis"
    assert config.providers[1]["plan"] == "basic"


def test_empty_config():
    """Test parsing empty configuration (all defaults)."""
    content = ""
    config = Hop3Config.from_str(content)

    assert config.metadata == {}
    assert config.build == {}
    assert config.run == {}
    assert config.env == {}
    assert config.port == {}
    assert config.providers == []
    assert config.get_workers_from_run_section() == {}


def test_has_section():
    """Test has_section() utility method."""
    content = """
[metadata]
id = "test"

[run]
start = "python app.py"
"""
    config = Hop3Config.from_str(content)

    assert config.has_section("metadata") is True
    assert config.has_section("run") is True
    assert config.has_section("build") is False
    assert config.has_section("env") is False


def test_to_dict():
    """Test to_dict() serialization."""
    content = """
[metadata]
id = "my-app"

[run]
start = "python app.py"
"""
    config = Hop3Config.from_str(content)
    config_dict = config.to_dict()

    assert "metadata" in config_dict
    assert "run" in config_dict
    assert "workers" in config_dict
    assert config_dict["metadata"]["id"] == "my-app"
    assert config_dict["workers"]["web"] == "python app.py"


def test_file_not_found():
    """Test error handling for missing file."""
    try:
        Hop3Config.from_file("/nonexistent/hop3.toml")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        assert "File not found" in str(e)


def test_repr():
    """Test __repr__ output."""
    content = """
[metadata]
id = "test"
"""
    config = Hop3Config.from_str(content)
    assert repr(config) == "<Hop3Config from_str>"

    # Test with file path would show path in repr
    # (tested implicitly in test_from_file)
