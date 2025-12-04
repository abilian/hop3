# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for hop3.toml configuration parser."""

from __future__ import annotations

import pytest

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


# =============================================================================
# WAF Configuration Tests
# =============================================================================


def test_waf_section_defaults():
    """Test default values when [waf] section is missing."""
    content = """
[metadata]
id = "test"
"""
    config = Hop3Config.from_str(content)

    assert config.waf_enabled is False
    assert config.waf_engine == "lewaf"
    assert config.waf_ruleset == "owasp-crs"
    assert config.waf_paranoia_level == 1
    assert config.waf_mode == "block"
    assert config.waf_exclusions == {}
    assert config.waf_crs == {}


def test_waf_section_full():
    """Test parsing complete [waf] section."""
    content = """
[waf]
enabled = true
engine = "coraza"
ruleset = "minimal"
paranoia_level = 2
mode = "detect"

[waf.exclusions]
paths = ["/api/webhook", "/health"]
rule_ids = [942100, 942200]

[waf.crs]
custom = 'SecRule REQUEST_URI "@contains /admin" "id:10001,deny,status:403"'
"""
    config = Hop3Config.from_str(content)

    assert config.waf_enabled is True
    assert config.waf_engine == "coraza"
    assert config.waf_ruleset == "minimal"
    assert config.waf_paranoia_level == 2
    assert config.waf_mode == "detect"
    assert config.waf_exclusions == {
        "paths": ["/api/webhook", "/health"],
        "rule_ids": [942100, 942200],
    }
    assert "custom" in config.waf_crs


def test_waf_section_partial():
    """Test parsing partial [waf] section with defaults."""
    content = """
[waf]
enabled = true
paranoia_level = 3
"""
    config = Hop3Config.from_str(content)

    assert config.waf_enabled is True
    assert config.waf_engine == "lewaf"  # default
    assert config.waf_ruleset == "owasp-crs"  # default
    assert config.waf_paranoia_level == 3
    assert config.waf_mode == "block"  # default


def test_security_rules_section():
    """Test [security.rules] section parsing."""
    content = """
[security.rules]
allow = ["/health", "/metrics"]
deny = ["/admin/debug", "/phpMyAdmin"]
allow_ips = ["10.0.0.0/8", "192.168.1.100"]
deny_ips = ["1.2.3.4", "5.6.7.8"]
"""
    config = Hop3Config.from_str(content)

    assert config.security_allow_paths == ["/health", "/metrics"]
    assert config.security_deny_paths == ["/admin/debug", "/phpMyAdmin"]
    assert config.security_allow_ips == ["10.0.0.0/8", "192.168.1.100"]
    assert config.security_deny_ips == ["1.2.3.4", "5.6.7.8"]


def test_security_rules_defaults():
    """Test default values for [security.rules]."""
    content = """
[metadata]
id = "test"
"""
    config = Hop3Config.from_str(content)

    assert config.security_allow_paths == []
    assert config.security_deny_paths == []
    assert config.security_allow_ips == []
    assert config.security_deny_ips == []


def test_get_waf_config():
    """Test get_waf_config() method returns complete config dict."""
    content = """
[waf]
enabled = true
engine = "lewaf"
ruleset = "owasp-crs"
paranoia_level = 2
mode = "block"

[waf.exclusions]
paths = ["/webhook"]
rule_ids = [942100]

[waf.crs]
custom = "SecRule ..."

[security.rules]
allow = ["/health"]
deny = ["/admin"]
allow_ips = ["10.0.0.0/8"]
deny_ips = ["1.2.3.4"]
"""
    config = Hop3Config.from_str(content)
    waf_config = config.get_waf_config("my-app")

    assert waf_config["app_name"] == "my-app"
    assert waf_config["enabled"] is True
    assert waf_config["engine"] == "lewaf"
    assert waf_config["ruleset"] == "owasp-crs"
    assert waf_config["paranoia_level"] == 2
    assert waf_config["mode"] == "block"
    assert waf_config["exclusions"] == ["/webhook"]
    assert waf_config["disabled_rules"] == [942100]
    assert waf_config["custom_rules"] == "SecRule ..."
    assert waf_config["allow_paths"] == ["/health"]
    assert waf_config["deny_paths"] == ["/admin"]
    assert waf_config["allow_ips"] == ["10.0.0.0/8"]
    assert waf_config["deny_ips"] == ["1.2.3.4"]


def test_get_waf_config_defaults():
    """Test get_waf_config() with default values."""
    content = ""
    config = Hop3Config.from_str(content)
    waf_config = config.get_waf_config("default-app")

    assert waf_config["app_name"] == "default-app"
    assert waf_config["enabled"] is False
    assert waf_config["engine"] == "lewaf"
    assert waf_config["ruleset"] == "owasp-crs"
    assert waf_config["paranoia_level"] == 1
    assert waf_config["mode"] == "block"
    assert waf_config["exclusions"] == []
    assert waf_config["disabled_rules"] == []
    assert waf_config["custom_rules"] == ""
    assert waf_config["allow_paths"] == []
    assert waf_config["deny_paths"] == []
    assert waf_config["allow_ips"] == []
    assert waf_config["deny_ips"] == []


def test_has_section_waf():
    """Test has_section() for waf and security sections."""
    content = """
[waf]
enabled = true

[security.rules]
allow = ["/health"]
"""
    config = Hop3Config.from_str(content)

    assert config.has_section("waf") is True
    assert config.has_section("security") is True


def test_has_section_waf_missing():
    """Test has_section() returns False when waf section missing."""
    content = """
[metadata]
id = "test"
"""
    config = Hop3Config.from_str(content)

    assert config.has_section("waf") is False
    assert config.has_section("security") is False
