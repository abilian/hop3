"""
This package contains the service layer of the hop3 server.

Some of the API is currently duplicated from the `hop3_agent` package
(this will be refactored in the future, as we move to a properly layered
architecture).
"""
from __future__ import annotations

from .api import get_app, list_apps
from .model import App

__all__ = ["App", "get_app", "list_apps"]
