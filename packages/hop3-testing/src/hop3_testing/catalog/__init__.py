# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test catalog system for hop3-testing.

This module provides:
- TestDefinition: Complete test definition parsed from test.toml
- Catalog: Discovers and indexes all tests in the project
- Loader: Parses test.toml files
"""

from __future__ import annotations

from .loader import load_test_definition
from .models import (
    Category,
    DemoConfig,
    DeploymentConfig,
    Priority,
    TargetType,
    TestDefinition,
    TestMetadata,
    TestRequirements,
    Tier,
    TutorialConfig,
    Validation,
    ValidationExpect,
)
from .scanner import Catalog

__all__ = [
    "Catalog",
    "Category",
    "DemoConfig",
    "DeploymentConfig",
    "Priority",
    "TargetType",
    "TestDefinition",
    "TestMetadata",
    "TestRequirements",
    "Tier",
    "TutorialConfig",
    "Validation",
    "ValidationExpect",
    "load_test_definition",
]
