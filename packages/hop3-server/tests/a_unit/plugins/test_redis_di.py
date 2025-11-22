# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for Redis DI integration."""

from __future__ import annotations

from unittest.mock import Mock

from dishka import Provider, Scope, make_container, provide

from hop3.config import HopConfig
from hop3.di import create_container
from hop3.plugins.redis.factory import RedisClientFactory


def test_redis_factory_from_config():
    """Test creating RedisClientFactory from HopConfig."""
    config = HopConfig()
    factory = RedisClientFactory.from_config(config)

    assert factory.host == config.redis_host
    assert factory.port == config.redis_port
    assert factory.max_connections == config.redis_max_connections


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
    factory = RedisClientFactory(
        host="testhost",
        port=6380,
    )

    params = factory.get_connection_params(db=1)

    assert params["db"] == 1
    assert "password" not in params


def test_redis_factory_get_url():
    """Test Redis URL generation."""
    factory = RedisClientFactory(
        host="testhost",
        port=6380,
        password="testpass",
    )

    # Without password
    url = factory.get_url(db=1, include_password=False)
    assert url == "redis://testhost:6380/1"

    # With password
    url_with_pass = factory.get_url(db=1, include_password=True)
    assert url_with_pass == "redis://:testpass@testhost:6380/1"


def test_redis_factory_provided_by_plugin():
    """Test that Redis plugin provides RedisClientFactory service."""
    # Use create_container() to get full plugin integration
    container = create_container()
    try:
        factory = container.get(RedisClientFactory)

        assert factory is not None
        assert isinstance(factory, RedisClientFactory)
        # Should use default config values
        assert factory.host == "localhost"
        assert factory.port == 6379
        assert factory.max_connections == 50
    finally:
        container.close()


def test_redis_factory_is_singleton():
    """Test that RedisClientFactory is a singleton in APP scope."""
    container = create_container()
    try:
        factory1 = container.get(RedisClientFactory)
        factory2 = container.get(RedisClientFactory)

        # Same instance due to APP scope
        assert factory1 is factory2
    finally:
        container.close()


def test_redis_factory_with_custom_config():
    """Test RedisClientFactory with custom configuration."""
    import os

    # Set custom config via environment
    os.environ["REDIS_HOST"] = "customhost"
    os.environ["REDIS_PORT"] = "6380"
    os.environ["REDIS_PASSWORD"] = "custompass"
    os.environ["REDIS_MAX_CONNECTIONS"] = "100"

    try:
        config = HopConfig()
        factory = RedisClientFactory.from_config(config)

        assert factory.host == "customhost"
        assert factory.port == 6380
        assert factory.password == "custompass"
        assert factory.max_connections == 100
    finally:
        # Clean up
        os.environ.pop("REDIS_HOST", None)
        os.environ.pop("REDIS_PORT", None)
        os.environ.pop("REDIS_PASSWORD", None)
        os.environ.pop("REDIS_MAX_CONNECTIONS", None)


def test_redis_factory_with_mock_provider():
    """Test RedisClientFactory with mocked provider for testing."""

    class MockRedisProvider(Provider):
        """Mock provider for testing."""

        scope = Scope.APP

        @provide
        def get_redis_factory(self) -> RedisClientFactory:
            mock = Mock(spec=RedisClientFactory)
            mock.host = "mockhost"
            mock.port = 9999
            mock.get_connection_params.return_value = {"host": "mockhost"}
            return mock

    container = make_container(MockRedisProvider())
    try:
        factory = container.get(RedisClientFactory)

        assert factory.host == "mockhost"
        assert factory.port == 9999

        params = factory.get_connection_params()
        assert params == {"host": "mockhost"}
        factory.get_connection_params.assert_called_once()
    finally:
        container.close()
