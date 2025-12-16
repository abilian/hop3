# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Screen modules for Hop3 TUI."""

from __future__ import annotations

from hop3_tui.screens.addons import AddonsScreen
from hop3_tui.screens.app_detail import AppDetailScreen
from hop3_tui.screens.apps import AppsScreen
from hop3_tui.screens.backups import BackupsScreen
from hop3_tui.screens.chat import ChatScreen
from hop3_tui.screens.dashboard import DashboardScreen
from hop3_tui.screens.env_vars import EnvVarsScreen
from hop3_tui.screens.logs import LogsScreen
from hop3_tui.screens.processes import ProcessesScreen
from hop3_tui.screens.system import SystemScreen
from hop3_tui.screens.system_logs import SystemLogsScreen

__all__ = [
    "AddonsScreen",
    "AppDetailScreen",
    "AppsScreen",
    "BackupsScreen",
    "ChatScreen",
    "DashboardScreen",
    "EnvVarsScreen",
    "LogsScreen",
    "ProcessesScreen",
    "SystemLogsScreen",
    "SystemScreen",
]
