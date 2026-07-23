# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared CLI utilities for addon plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.lib import echo

if TYPE_CHECKING:
    from hop3.core.protocols import Addon


def display_credentials(addon: Addon) -> None:
    """
    Display connection credentials for an addon, masking passwords.

    Args:
        addon: The addon instance to display credentials for
    """
    try:
        details = addon.get_connection_details()

        for key, value in details.items():
            # Mask password in display
            if "PASSWORD" in key.upper():
                echo(f"{key}: {'*' * 8}")
            else:
                echo(f"{key}: {value}")

    except RuntimeError as e:
        echo(f"Error: {e}")
    except Exception as e:
        echo(f"Unexpected error: {e}")
