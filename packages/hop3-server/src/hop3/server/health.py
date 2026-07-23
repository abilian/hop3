# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Addon health checks for server startup.

This module discovers and runs health checks from plugins to verify that
configured services (MySQL, PostgreSQL, Redis, etc.) are accessible.
Health checks are run:
- During server startup (warnings logged for failures)
- Via the `system check` command

Health checks are contributed by plugins via the `get_health_checks()` hook.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hop3.core.plugins import get_plugin_manager
from hop3.core.protocols import HealthCheckResult

if TYPE_CHECKING:
    from hop3.core.protocols import HealthCheck

logger = logging.getLogger(__name__)


def get_all_health_checks() -> list[HealthCheck]:
    """
    Discover all health checks from plugins.

    Returns:
        List of HealthCheck instances from all registered plugins.
    """
    pm = get_plugin_manager()
    health_checks: list[HealthCheck] = []

    for check_list in pm.hook.get_health_checks():
        health_checks.extend(check_list)

    return health_checks


def run_health_check(check: HealthCheck) -> HealthCheckResult:
    """
    Run a single health check safely.

    Args:
        check: The health check to run.

    Returns:
        HealthCheckResult from the check, or a failure result if check raises.
    """
    try:
        return check.check()
    except Exception as e:
        logger.exception("Health check %s raised exception", check.name)
        return HealthCheckResult(
            name=check.name,
            passed=False,
            message=f"Health check raised exception: {e}",
        )


def verify_addon_health() -> dict[str, HealthCheckResult]:
    """
    Verify all configured addon services are accessible.

    Discovers health checks from plugins and runs each one.
    Called during server startup to provide early detection of
    configuration issues.

    Returns:
        Dictionary mapping check name to HealthCheckResult.
    """
    results: dict[str, HealthCheckResult] = {}

    health_checks = get_all_health_checks()

    for check in health_checks:
        result = run_health_check(check)
        results[check.name] = result

        # Log result
        if result.passed:
            logger.info("%s health check passed: %s", result.name, result.message)
        else:
            logger.warning(
                "%s health check failed: %s. Apps using this service will fail to deploy.",
                result.name,
                result.message,
            )

    # Log summary
    failed = [name for name, result in results.items() if not result.passed]
    if failed:
        logger.warning(
            "Addon health check failed for: %s. "
            "Check hop3-server.toml configuration and service status.",
            ", ".join(failed),
        )
    elif results:
        logger.info("All addon health checks passed")
    else:
        logger.debug("No addon health checks registered")

    return results
