# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Screen modules for Hop3 TUI."""

from __future__ import annotations

from hop3_tui.screens.app_detail import AppDetailScreen
from hop3_tui.screens.apps import AppsScreen
from hop3_tui.screens.chat import ChatScreen
from hop3_tui.screens.dashboard import DashboardScreen
from hop3_tui.screens.logs import LogsScreen
from hop3_tui.screens.system import SystemScreen

__all__ = [
    "AppDetailScreen",
    "AppsScreen",
    "ChatScreen",
    "DashboardScreen",
    "LogsScreen",
    "SystemScreen",
]
