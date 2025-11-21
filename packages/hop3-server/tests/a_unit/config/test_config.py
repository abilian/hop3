# Copyright (c) 2024-2025, Abilian SAS


from __future__ import annotations

from pathlib import Path

from hop3.lib.config import Config


def test_parse_config_file():
    config_file = Path(__file__).parent / "config.toml"
    config = Config(file=config_file)
    assert config.get("TOTO") == "titi"


def test_default(monkeypatch):
    """Test default configuration values.

    Note: This test ensures HOP3_ROOT is set to the expected test default
    regardless of environment variables.
    """
    from hop3.config import HopConfig

    # Ensure HOP3_ROOT environment variable is set to test default
    monkeypatch.setenv("HOP3_ROOT", "/tmp/hop3")

    # Reset and recreate config to pick up the environment variable
    HopConfig.reset_instance()
    test_config = HopConfig()
    HopConfig.set_instance(test_config)

    # Access config via the singleton instance (not module-level constants)
    cfg = HopConfig.get_instance()

    assert cfg.HOP3_USER == "hop3"
    assert Path("/tmp/hop3/bin") == cfg.HOP3_BIN
    assert cfg.HOP3_SCRIPT == "/tmp/hop3/venv/bin/hop-agent"
    assert Path("/tmp/hop3/apps") == cfg.APP_ROOT

    assert Path("/tmp/hop3/nginx") == cfg.NGINX_ROOT
    assert Path("/tmp/hop3/cache") == cfg.CACHE_ROOT

    assert Path("/tmp/hop3/uwsgi-available") == cfg.UWSGI_AVAILABLE
    assert Path("/tmp/hop3/uwsgi-enabled") == cfg.UWSGI_ENABLED
    assert Path("/tmp/hop3/uwsgi") == cfg.UWSGI_ROOT

    assert cfg.ACME_ENGINE == "self-signed"
    assert cfg.ACME_ROOT_CA == "letsencrypt.org"

    # Cleanup
    HopConfig.reset_instance()
