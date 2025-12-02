# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""ASGI entry point for Litestar CLI auto-discovery.

This module provides a canonical asgi.py at the project root for easy
development with Litestar CLI. Just run: `uv run litestar run --reload`
"""

from __future__ import annotations

from hop3.server.asgi import create_app

# Create app instance for Litestar CLI
app = create_app()
