# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for hop3.toml configuration parser."""

from __future__ import annotations

import pytest
import tomllib

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlSchema, Hop3TomlValidationError


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


def test_run_section_static_paths():
    """Test [run] static path parsing."""
    content = """
[run]
start = "gunicorn app:app"
static = {"/static" = "static/", "/media" = "media/"}
"""
    config = Hop3Config.from_str(content)

    assert config.static_paths == {"/static": "static/", "/media": "media/"}


def test_run_section_healthcheck():
    """Test [run] healthcheck parsing."""
    content = """
[run]
start = "gunicorn app:app"
healthcheck = "/health"
healthcheck-timeout = 60
"""
    config = Hop3Config.from_str(content)

    assert config.healthcheck_path == "/health"
    assert config.healthcheck_timeout == 60


def test_run_section_healthcheck_defaults():
    """Test [run] healthcheck defaults when not specified."""
    content = """
[run]
start = "gunicorn app:app"
"""
    config = Hop3Config.from_str(content)

    assert config.healthcheck_path == ""
    assert config.healthcheck_timeout == 30  # default


def test_run_section_static_empty():
    """Test static_paths returns empty dict when not specified."""
    content = """
[run]
start = "gunicorn app:app"
"""
    config = Hop3Config.from_str(content)

    assert config.static_paths == {}


def test_run_section_complete():
    """Test complete [run] section with all fields."""
    content = """
[run]
start = "gunicorn config.wsgi:application"
before-run = ["python manage.py migrate"]
static = {"/static" = "staticfiles/", "/media" = "media/"}
healthcheck = "/health/"
healthcheck-timeout = 120
packages = ["postgresql"]
"""
    config = Hop3Config.from_str(content)

    assert config.start_command == "gunicorn config.wsgi:application"
    assert config.before_run_commands == ["python manage.py migrate"]
    assert config.static_paths == {"/static": "staticfiles/", "/media": "media/"}
    assert config.healthcheck_path == "/health/"
    assert config.healthcheck_timeout == 120
    assert config.run_packages == ["postgresql"]


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

    # NOTE: prebuild is NOT included in workers because build.before-build
    # is handled by deployer.py._run_hook() during the build phase, not as a worker
    assert workers == {
        "web": "npm start",
        "prerun": "npm run migrate",
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


def test_addons_section():
    """Test [[addons]] section parsing."""
    content = """
[[addons]]
type = "postgres"

[[addons]]
type = "redis"

[[addons]]
type = "mysql"
name = "custom-mysql"
"""
    config = Hop3Config.from_str(content)

    assert len(config.addons) == 3
    assert config.addons[0]["type"] == "postgres"
    assert config.addons[1]["type"] == "redis"
    assert config.addons[2]["type"] == "mysql"
    assert config.addons[2]["name"] == "custom-mysql"


def test_addons_fallback_to_provider():
    """Test that addons falls back to [[provider]] for backwards compatibility."""
    content = """
[[provider]]
type = "postgres"
"""
    config = Hop3Config.from_str(content)

    # Should use providers as fallback when addons is empty
    assert len(config.addons) == 1
    assert config.addons[0]["type"] == "postgres"


def test_addons_prefers_addons_over_provider():
    """Test that [[addons]] takes precedence over [[provider]]."""
    content = """
[[addons]]
type = "mysql"

[[provider]]
type = "postgres"
"""
    config = Hop3Config.from_str(content)

    # Should use addons, not providers
    assert len(config.addons) == 1
    assert config.addons[0]["type"] == "mysql"


def test_get_addon_types():
    """Test get_addon_types() returns list of addon type names."""
    content = """
[[addons]]
type = "postgres"

[[addons]]
type = "redis"

[[addons]]
type = "mysql"
"""
    config = Hop3Config.from_str(content)

    addon_types = config.get_addon_types()
    assert addon_types == ["postgres", "redis", "mysql"]


def test_get_addon_types_empty():
    """Test get_addon_types() returns empty list when no addons."""
    content = ""
    config = Hop3Config.from_str(content)

    assert config.get_addon_types() == []


def test_get_addon_types_skips_missing_type():
    """Test get_addon_types() skips addons without type key."""
    content = """
[[addons]]
type = "postgres"

[[addons]]
name = "no-type-addon"
"""
    config = Hop3Config.from_str(content)

    addon_types = config.get_addon_types()
    assert addon_types == ["postgres"]


def test_empty_config():
    """Test parsing empty configuration (all defaults)."""
    content = ""
    config = Hop3Config.from_str(content)

    assert config.metadata == {}
    assert config.build == {}
    assert config.run == {}
    assert config.env == {}
    assert config.port == {}
    assert config.addons == []
    assert config.providers == []
    assert config.get_addon_types() == []
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

[[addons]]
type = "postgres"
"""
    config = Hop3Config.from_str(content)
    config_dict = config.to_dict()

    assert "metadata" in config_dict
    assert "run" in config_dict
    assert "workers" in config_dict
    assert "addons" in config_dict
    assert config_dict["metadata"]["id"] == "my-app"
    assert config_dict["workers"]["web"] == "python app.py"
    assert len(config_dict["addons"]) == 1
    assert config_dict["addons"][0]["type"] == "postgres"


def test_file_not_found():
    """Test error handling for missing file."""

    with pytest.raises(FileNotFoundError, match="File not found"):
        Hop3Config.from_file("/nonexistent/hop3.toml")


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


def test_test_validation_status_in_snake():
    """`[test.validations]` accepts `status_in = [...]` — the form xwiki
    uses to handle its first-boot 202 → 200 transition."""
    c = Hop3TomlSchema.model_validate(
        tomllib.loads(
            """
[test]
[[test.validations]]
path = "/"
status_in = [200, 202]
"""
        )
    )
    assert c.test.validations[0].status_in == [200, 202]


def test_test_validation_status_in_kebab_alias():
    """Kebab-case `status-in` is accepted alongside the snake form."""
    c = Hop3TomlSchema.model_validate(
        tomllib.loads(
            """
[[test.validations]]
path = "/"
status-in = [200, 503]
"""
        )
    )
    assert c.test.validations[0].status_in == [200, 503]


def test_test_section_expects_failure():
    """`expects-failure` in `[test]` flags negative-test-case fixtures."""
    c = Hop3TomlSchema.model_validate(
        tomllib.loads(
            """
[test]
expects-failure = true
"""
        )
    )
    assert c.test.expects_failure is True


def test_test_validation_rejects_unknown_field():
    """`extra = 'forbid'` must still reject typos / unknown fields."""
    with pytest.raises((ValueError, Hop3TomlValidationError)):
        Hop3TomlSchema.model_validate(
            tomllib.loads(
                """
[[test.validations]]
path = "/"
not_a_real_field = 42
"""
            )
        )
