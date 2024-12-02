# Copyright (c) 2024, Abilian SAS

# ruff: noqa: SIM300

from __future__ import annotations

from pathlib import Path

from hop3.config import Config


def test_default():
    config = Config()

    assert config.HOP3_USER == "hop3"
    assert Path("/home/hop3/bin") == config.HOP3_BIN
    assert config.HOP3_SCRIPT == "/home/hop3/venv/bin/hop-agent"
    assert Path("/home/hop3/apps") == config.APP_ROOT

    assert Path("/home/hop3/nginx") == config.NGINX_ROOT
    assert Path("/home/hop3/cache") == config.CACHE_ROOT

    assert Path("/home/hop3/uwsgi-available") == config.UWSGI_AVAILABLE
    assert Path("/home/hop3/uwsgi-enabled") == config.UWSGI_ENABLED
    assert Path("/home/hop3/uwsgi") == config.UWSGI_ROOT

    assert Path("/home/hop3/.acme.sh") == config.ACME_ROOT
    assert Path("/home/hop3/acme") == config.ACME_WWW
    assert config.ACME_ROOT_CA == "letsencrypt.org"


def test_alt_home():
    config = Config()
    config.set_home(Path("/tmp/hop3"))
    assert config.NGINX_ROOT == Path("/tmp/hop3/nginx")


def test_read_toml():
    config_path = Path(__file__).parent / "hop3-config.toml"
    config = Config()
    config.read_toml(config_path)

    # Default values
    assert config.HOP3_USER == "hop3"

    # Values from toml
    assert config.get("database_uri", "sqlite...").startswith("postgresql://")
