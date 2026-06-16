# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Litestar controllers for Hop3 server."""

from __future__ import annotations

from .auth import AuthController

# Alias for backward compatibility
from .catalog import CatalogController
from .dashboard import (
    AddonsController,
    AppsController,
    BackupsController,
    CertificatesController,
    DashboardIndexController,
    EnvVarsController,
    LogsController,
)
from .root import RootController
from .rpc import RPCController
from .stream import StreamController

__all__ = [
    "AddonsController",
    "AppsController",
    "AuthController",
    "BackupsController",
    "CatalogController",
    "CertificatesController",
    "DashboardIndexController",
    "EnvVarsController",
    "LogsController",
    "RPCController",
    "RootController",
    "StreamController",
]
