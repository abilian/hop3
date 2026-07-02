# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Hop3 cloud system-test framework.

End-to-end testing infrastructure for Hop3 on real Hetzner Cloud servers.
Cloud runs go through `hop3-test run --provider hetzner` (single) and
`hop3-test matrix` (image sweep); this subpackage provides the Hetzner
lifecycle (rebuild/wait), the shared deploy wrapper, and provisioning
(ADR 052 7b.7).

Example usage:
    from hop3_testing.system_tests.provision import provision_server

    ip = provision_server(provider="hetzner", server_id=123, image="ubuntu-24.04")
    # then deploy + test against `ip` via a RemoteTarget (what `run` does)
"""

from __future__ import annotations

from .config import Config, DeploymentConfig, HetznerConfig, TestConfig, load_config
from .deployment import DeploymentManager, DeploymentResult
from .diagnostics import DiagnosticCollector, DiagnosticResult, collect_diagnostics
from .hetzner import HetznerManager, ServerInfo
from .hetzner_cli import main
from .provision import provision_server
from .runner import AllSuitesResult, TestRunnerManager, TestSuiteResult

__all__ = [
    # Test Runner
    "AllSuitesResult",
    # Config
    "Config",
    "DeploymentConfig",
    # Deployment
    "DeploymentManager",
    "DeploymentResult",
    # Diagnostics
    "DiagnosticCollector",
    "DiagnosticResult",
    "HetznerConfig",
    # Hetzner
    "HetznerManager",
    "ServerInfo",
    "TestConfig",
    "TestRunnerManager",
    "TestSuiteResult",
    "collect_diagnostics",
    "load_config",
    # CLI
    "main",
    # Provisioning (ADR 052 7b.7)
    "provision_server",
]
