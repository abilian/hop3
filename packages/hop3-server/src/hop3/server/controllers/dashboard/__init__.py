# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard controllers package.

This package contains controllers for the dashboard web interface:
- DashboardIndexController: Main dashboard with app list
- AppsController: App CRUD and management
- LogsController: Log viewing and streaming
- EnvVarsController: Environment variable management
- AddonsController: Addon management
- BackupsController: Backup management
"""

from __future__ import annotations

from .addons import AddonsController
from .apps import AppsController
from .backups import BackupsController
from .certificates import CertificatesController
from .env_vars import EnvVarsController
from .index import DashboardIndexController
from .logs import LogsController

__all__ = [
    "AddonsController",
    "AppsController",
    "BackupsController",
    "CertificatesController",
    "DashboardIndexController",
    "EnvVarsController",
    "LogsController",
]
