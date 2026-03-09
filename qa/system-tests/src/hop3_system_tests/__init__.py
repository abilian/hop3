# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Hop3 Daily System Test Framework.

This package provides end-to-end testing infrastructure for Hop3,
running tests on real Hetzner Cloud servers.

Example usage:
    from hop3_system_tests import Config, run_daily_test

    config = Config.from_env()
    result = run_daily_test(config)

    if result.success:
        print("All tests passed!")
    else:
        print(f"Failed at phase: {result.failed_phase}")
"""

from .cli import main
from .config import Config, DeploymentConfig, HetznerConfig, TestConfig, load_config
from .deployment import DeploymentManager, DeploymentResult
from .hetzner import HetznerManager, ServerInfo
from .orchestrator import DailyTestOrchestrator, DailyTestResult, run_daily_test
from .runner import AllSuitesResult, TestRunnerManager, TestSuiteResult

__all__ = [
    # CLI
    "main",
    # Config
    "Config",
    "DeploymentConfig",
    "HetznerConfig",
    "TestConfig",
    "load_config",
    # Hetzner
    "HetznerManager",
    "ServerInfo",
    # Deployment
    "DeploymentManager",
    "DeploymentResult",
    # Orchestrator
    "DailyTestOrchestrator",
    "DailyTestResult",
    "run_daily_test",
    # Test Runner
    "AllSuitesResult",
    "TestRunnerManager",
    "TestSuiteResult",
]

__version__ = "0.1.0"
