# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Litestar controllers for Hop3 server."""

from __future__ import annotations

from .auth import AuthController
from .dashboard import (
    AddonsController,
    AppsController,
    BackupsController,
    DashboardIndexController,
    EnvVarsController,
    LogsController,
)

# Alias for backward compatibility
from .marketplace import MarketplaceController
from .root import RootController
from .rpc import RPCController
from .stream import StreamController

__all__ = [
    "AddonsController",
    "AppsController",
    "AuthController",
    "BackupsController",
    "DashboardIndexController",
    "EnvVarsController",
    "LogsController",
    "MarketplaceController",
    "RPCController",
    "RootController",
    "StreamController",
]
