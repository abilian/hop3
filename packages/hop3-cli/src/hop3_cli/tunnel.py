# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Backward compatibility shim - import from hop3_cli.rpc instead."""

from __future__ import annotations

from .rpc.tunnel import SSHTunnel, find_free_port

__all__ = ["SSHTunnel", "find_free_port"]
