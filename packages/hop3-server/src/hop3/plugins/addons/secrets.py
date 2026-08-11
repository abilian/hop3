# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Shared secrets management for addon plugins.

This module provides utilities for storing and retrieving addon secrets
(passwords, connection strings, etc.) in a secure manner.

Secrets are stored in HOP3_ROOT/addons/<addon_type>/<addon_name>.json
with restrictive file permissions (0o600).

**This store holds plaintext.** It is the provisioning-side record of a
backing service (the password the addon created in PostgreSQL/MySQL, the
operator's upstream SMTP credentials), and it is the source those values are
read back from. The Fernet-encrypted ``AddonCredential`` rows are the *app
attachment* copy; the two are separate stores, and only one of them is
encrypted. See ``notes/security/security-model.md`` §3.4.7 for what that does
and does not defend against.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
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
    Atomically save secrets for an addon, 0600 from birth.

    Written the way every other credential file in the workspace is written
    (``server/cli/setup.py``, the CLI's credential store): ``mkstemp`` creates
    the temp file 0600 regardless of umask and ``os.replace`` swaps it in.

    The previous open-then-chmod left the password world-readable for the
    length of the write, and re-opened that window on every rotation. It also
    truncated the live file first, so a failed write destroyed the credential
    it was replacing rather than leaving the old one in place.

    Args:
        addon_type: The type of addon (e.g., "mysql", "postgres")
        addon_name: The unique name of the addon instance
        secrets_data: Dictionary of secrets to store
    """
    secrets_file = _get_secrets_file(addon_type, addon_name)
    fd, tmp = tempfile.mkstemp(
        prefix=f".{addon_name}.", suffix=".tmp", dir=secrets_file.parent
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(secrets_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, secrets_file)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


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
