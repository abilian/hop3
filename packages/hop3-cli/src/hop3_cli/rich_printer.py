# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Backward compatibility shim - import from hop3_cli.ui instead."""

from __future__ import annotations

from .ui.rich_printer import Message, RichPrinter

__all__ = ["Message", "RichPrinter"]
