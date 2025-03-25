# Copyright (c) 2024-2025, Abilian SAS

# ruff: noqa: SIM300

from __future__ import annotations

from pathlib import Path

from hop3 import config
from hop3.lib.config import Config


def test_parse_config_file():
    config_file = Path(__file__).parent / "config.toml"
    config = Config(file=config_file)
    assert config.get("TOTO") == "titi"


def test_default():
    assert config.HOP3_USER == "hop3"
    assert Path("/tmp/hop3/bin") == config.HOP3_BIN
    assert config.HOP3_SCRIPT == "/tmp/hop3/venv/bin/hop-agent"
    assert Path("/tmp/hop3/apps") == config.APP_ROOT

    assert Path("/tmp/hop3/nginx") == config.NGINX_ROOT
    assert Path("/tmp/hop3/cache") == config.CACHE_ROOT

    assert Path("/tmp/hop3/uwsgi-available") == config.UWSGI_AVAILABLE
    assert Path("/tmp/hop3/uwsgi-enabled") == config.UWSGI_ENABLED
    assert Path("/tmp/hop3/uwsgi") == config.UWSGI_ROOT

    assert config.ACME_ENGINE == "self-signed"
    assert config.ACME_ROOT_CA == "letsencrypt.org"
