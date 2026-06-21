# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test Lab controllers."""

from __future__ import annotations

from .auth import AuthController
from .builds import BuildController
from .bundle import BundleController
from .dashboard import DashboardController, HealthController
from .profiles import ProfilesController
from .queue import QueueController
from .running import RunningController
from .runs import RunsController
from .servers import ServersController
from .trends import TrendsController

__all__ = [
    "AuthController",
    "BuildController",
    "BundleController",
    "DashboardController",
    "HealthController",
    "ProfilesController",
    "QueueController",
    "RunningController",
    "RunsController",
    "ServersController",
    "TrendsController",
]
