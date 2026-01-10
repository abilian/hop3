# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test runners for hop3-testing.

This module provides runners for different test categories:
- DeploymentTestRunner: Deploy apps and run validations
- DemoTestRunner: Execute demo scripts or declarative demos
- TutorialTestRunner: Run tutorials via validoc
"""

from __future__ import annotations

from .base import TestResult, ValidationResult
from .demo import DemoTestRunner
from .deployment import DeploymentTestRunner
from .tutorial import TutorialTestRunner
from .validations import run_validation

__all__ = [
    "DemoTestRunner",
    "DeploymentTestRunner",
    "TestResult",
    "TutorialTestRunner",
    "ValidationResult",
    "run_validation",
]
