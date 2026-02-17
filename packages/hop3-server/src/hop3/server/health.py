# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Addon health checks for server startup.

This module verifies that configured database addons (MySQL, PostgreSQL)
are accessible when the server starts. This provides early detection of
configuration issues rather than failing during app deployment.
"""

from __future__ import annotations

import logging

from hop3.plugins.mysql.admin import MySQLAdmin
from hop3.plugins.postgresql.admin import PostgresAdmin

logger = logging.getLogger(__name__)

# Optional dependency availability flags
_MYSQL_AVAILABLE = False
_PSYCOPG2_AVAILABLE = False
_REDIS_AVAILABLE = False

try:
    import mysql.connector

    _MYSQL_AVAILABLE = True
except ImportError:
    mysql = None  # type: ignore[assignment]

try:
    import psycopg2

    _PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

try:
    import redis

    _REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore[assignment]


def check_mysql_health() -> bool:
    """Check MySQL connectivity if configured.

    Returns:
        True if MySQL is accessible or not configured, False if configured but failing.
    """
    if not _MYSQL_AVAILABLE:
        logger.debug("MySQL connector not installed, skipping health check")
        return True

    try:
        admin = MySQLAdmin.from_config()

        # If no password configured, MySQL addon is not enabled
        if not admin.superuser_password:
            logger.debug("MySQL not configured (no superuser password)")
            return True

        # Try to connect
        connection = None
        try:
            connection = mysql.connector.connect(**admin.get_connection_params())
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            logger.info("MySQL health check passed")
            return True
        except mysql.connector.Error as e:
            logger.warning(
                "MySQL configured but connection failed: %s. "
                "Apps using MySQL addons will fail to deploy.",
                e,
            )
            return False
        finally:
            if connection:
                connection.close()

    except Exception as e:
        logger.warning("MySQL health check error: %s", e)
        return False


def check_postgres_health() -> bool:
    """Check PostgreSQL connectivity if configured.

    Returns:
        True if PostgreSQL is accessible or not configured, False if configured but failing.
    """
    if not _PSYCOPG2_AVAILABLE:
        logger.debug("psycopg2 not installed, skipping health check")
        return True

    try:
        admin = PostgresAdmin.from_config()

        # If no password configured, PostgreSQL addon is not enabled
        if not admin.superuser_password:
            logger.debug("PostgreSQL not configured (no superuser password)")
            return True

        # Try to connect
        connection = None
        try:
            connection = psycopg2.connect(**admin.get_connection_params())
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            logger.info("PostgreSQL health check passed")
            return True
        except psycopg2.Error as e:
            logger.warning(
                "PostgreSQL configured but connection failed: %s. "
                "Apps using PostgreSQL addons will fail to deploy.",
                e,
            )
            return False
        finally:
            if connection:
                connection.close()

    except Exception as e:
        logger.warning("PostgreSQL health check error: %s", e)
        return False


def check_redis_health() -> bool:
    """Check Redis connectivity.

    Redis doesn't require explicit configuration in hop3-server.toml,
    but if redis package is installed, we verify it's accessible.

    Returns:
        True if Redis is accessible or not installed, False if installed but failing.
    """
    if not _REDIS_AVAILABLE:
        logger.debug("Redis package not installed, skipping health check")
        return True

    try:
        client = redis.Redis(host="localhost", port=6379, socket_timeout=2)
        client.ping()
        logger.info("Redis health check passed")
        return True
    except Exception as e:
        # Redis not running or not accessible - this is OK if no apps use it
        logger.debug("Redis not accessible: %s", e)
        return True


def verify_addon_health() -> dict[str, bool]:
    """Verify all configured addon services are accessible.

    Called during server startup to provide early detection of
    configuration issues.

    Returns:
        Dictionary mapping addon name to health status.
    """
    results = {
        "mysql": check_mysql_health(),
        "postgresql": check_postgres_health(),
        "redis": check_redis_health(),
    }

    # Log summary
    failed = [name for name, ok in results.items() if not ok]
    if failed:
        logger.warning(
            "Addon health check failed for: %s. "
            "Check hop3-server.toml configuration and service status.",
            ", ".join(failed),
        )
    else:
        logger.info("All addon health checks passed")

    return results
