# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for Redis DI integration."""

from __future__ import annotations

import pytest

from hop3.di import create_container
from hop3.lib.config import Config
from hop3.plugins.redis import redis as redis_mod
from hop3.plugins.redis.factory import RedisClientFactory


def test_redis_factory_from_config():
    """Test creating RedisClientFactory from Config."""
    config = Config(env_prefix="REDIS_")
    factory = RedisClientFactory.from_config(config)

    assert factory.host == "127.0.0.1"
    assert factory.port == 6379
    assert factory.max_connections == 50


def test_redis_factory_loads_password_from_file_when_env_unset(monkeypatch):
    """The requirepass password lives in /etc/hop3/redis-pass, not REDIS_PASSWORD.

    Regression: the `system status` Redis health check connected with no
    password and an auth-enabled Redis rejected it ("HELLO must be called ...
    authenticated"). from_config must fall back to the password file.
    """
    monkeypatch.setattr(redis_mod, "_load_redis_password", lambda: "filepass")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    factory = RedisClientFactory.from_config(Config(env_prefix="REDIS_"))
    assert factory.password == "filepass"
    assert factory.get_connection_params()["password"] == "filepass"


def test_redis_factory_env_password_overrides_file(monkeypatch):
    """An explicit REDIS_PASSWORD still wins over the password file."""
    monkeypatch.setattr(redis_mod, "_load_redis_password", lambda: "filepass")
    monkeypatch.setenv("REDIS_PASSWORD", "envpass")

    factory = RedisClientFactory.from_config(Config(env_prefix="REDIS_"))
    assert factory.password == "envpass"


def test_redis_factory_get_connection_params():
    """Test RedisClientFactory connection parameters."""
    factory = RedisClientFactory(
        host="testhost",
        port=6380,
        password="testpass",
        max_connections=100,
    )

    params = factory.get_connection_params()

    assert params["host"] == "testhost"
    assert params["port"] == 6380
    assert params["db"] == 0
    assert params["password"] == "testpass"
    assert params["max_connections"] == 100
    assert params["decode_responses"] is True


def test_redis_factory_get_connection_params_no_password():
    """Test connection parameters without password."""
    factory = RedisClientFactory(host="testhost", port=6380)

    params = factory.get_connection_params(db=1)

    assert params["db"] == 1
    assert "password" not in params


@pytest.fixture
def container():
    """Create container with plugin providers."""
    container = create_container()
    yield container
    container.close()


def test_redis_factory_provided_by_plugin(container):
    """Test that Redis plugin provides RedisClientFactory service."""
    factory = container.get(RedisClientFactory)

    assert isinstance(factory, RedisClientFactory)
    assert factory.host == "127.0.0.1"
    assert factory.port == 6379
    assert factory.max_connections == 50


def test_redis_factory_is_singleton(container):
    """Test that RedisClientFactory is a singleton in APP scope."""
    factory1 = container.get(RedisClientFactory)
    factory2 = container.get(RedisClientFactory)

    assert factory1 is factory2
