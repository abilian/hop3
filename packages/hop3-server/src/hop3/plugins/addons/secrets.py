# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Shared secrets management for addon plugins.

This module provides utilities for storing and retrieving addon secrets
(passwords, connection strings, etc.) in a secure manner.

Secrets are stored in HOP3_ROOT/addons/<addon_type>/<addon_name>.json
with restrictive file permissions (0o600).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from hop3.config import HOP3_ROOT

if TYPE_CHECKING:
    from pathlib import Path


def _get_secrets_dir(addon_type: str) -> Path:
    """
    Get the directory for storing addon secrets.

    Args:
        addon_type: The type of addon (e.g., "mysql", "postgres", "redis")

    Returns:
        Path to the secrets directory, created if it doesn't exist
    """
    secrets_dir = HOP3_ROOT / "addons" / addon_type
    secrets_dir.mkdir(parents=True, exist_ok=True)
    return secrets_dir


def _get_secrets_file(addon_type: str, addon_name: str) -> Path:
    """
    Get the secrets file path for an addon.

    Args:
        addon_type: The type of addon (e.g., "mysql", "postgres")
        addon_name: The unique name of the addon instance

    Returns:
        Path to the secrets JSON file
    """
    return _get_secrets_dir(addon_type) / f"{addon_name}.json"


def load_addon_secrets(addon_type: str, addon_name: str) -> dict[str, Any] | None:
    """
    Load stored secrets for an addon.

    Args:
        addon_type: The type of addon (e.g., "mysql", "postgres")
        addon_name: The unique name of the addon instance

    Returns:
        Dictionary of secrets if file exists, None otherwise
    """
    secrets_file = _get_secrets_file(addon_type, addon_name)
    if secrets_file.exists():
        with secrets_file.open() as f:
            return json.load(f)
    return None


def save_addon_secrets(
    addon_type: str, addon_name: str, secrets_data: dict[str, Any]
) -> None:
    """
    Save secrets for an addon.

    The secrets file is created with restrictive permissions (0o600)
    to protect sensitive data.

    Args:
        addon_type: The type of addon (e.g., "mysql", "postgres")
        addon_name: The unique name of the addon instance
        secrets_data: Dictionary of secrets to store
    """
    secrets_file = _get_secrets_file(addon_type, addon_name)
    with secrets_file.open("w") as f:
        json.dump(secrets_data, f, indent=2)
    secrets_file.chmod(0o600)


def delete_addon_secrets(addon_type: str, addon_name: str) -> None:
    """
    Delete stored secrets for an addon.

    Args:
        addon_type: The type of addon (e.g., "mysql", "postgres")
        addon_name: The unique name of the addon instance
    """
    secrets_file = _get_secrets_file(addon_type, addon_name)
    if secrets_file.exists():
        secrets_file.unlink()


def list_addon_instances() -> list[tuple[str, str]]:
    """
    List all provisioned addon instances.

    The secrets store (HOP3_ROOT/addons/<type>/<name>.json) is the de-facto
    registry of provisioned instances, so enumerating it works for every
    addon type without per-plugin support.

    Returns:
        Sorted list of (addon_type, addon_name) pairs.
    """
    addons_dir = HOP3_ROOT / "addons"
    if not addons_dir.exists():
        return []

    instances: list[tuple[str, str]] = []
    for type_dir in sorted(addons_dir.iterdir()):
        if not type_dir.is_dir():
            continue
        for secrets_file in sorted(type_dir.glob("*.json")):
            instances.append((type_dir.name, secrets_file.stem))
    return instances
