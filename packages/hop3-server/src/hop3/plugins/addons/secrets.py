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

from hop3 import config as c

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _get_secrets_dir(addon_type: str) -> Path:
    """
    Get the directory for storing addon secrets.

    Args:
        addon_type: The type of addon (e.g., "mysql", "postgres", "redis")

    Returns:
        Path to the secrets directory, created if it doesn't exist
    """
    secrets_dir = c.HOP3_ROOT / "addons" / addon_type
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


def addon_secrets_exist(addon_type: str, addon_name: str) -> bool:
    """
    True if the addon's secrets file is present, readable or not.

    "Does this addon exist" must not depend on the file parsing: a corrupt
    file is still an addon that destroy has to remove.
    """
    return _get_secrets_file(addon_type, addon_name).exists()


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
    addons_dir = c.HOP3_ROOT / "addons"
    if not addons_dir.exists():
        return []

    instances: list[tuple[str, str]] = []
    for type_dir in sorted(addons_dir.iterdir()):
        if not type_dir.is_dir():
            continue
        for secrets_file in sorted(type_dir.glob("*.json")):
            instances.append((type_dir.name, secrets_file.stem))
    return instances


def find_identifier_clash(
    addon_type: str,
    addon_name: str,
    derive: Callable[[str], tuple[str, ...]],
) -> str | None:
    """
    Name another ``addon_type`` instance that would share ``addon_name``'s identifiers.

    ``derive`` maps an addon name to the identifiers the backing service
    stores (database, user, ...), as the service stores them: ``a-b`` and
    ``a_b`` both become the database ``a_b``, and a long name loses its tail
    to the service's length limit. Identifiers are compared position by
    position, so a database never clashes with a user of the same spelling.
    """
    mine = derive(addon_name)
    for other_type, other_name in list_addon_instances():
        if other_type != addon_type or other_name == addon_name:
            continue
        if any(a == b for a, b in zip(derive(other_name), mine, strict=True)):
            return other_name
    return None


def refuse_identifier_clash(
    addon_type: str,
    addon_name: str,
    derive: Callable[[str], tuple[str, str]],
    *,
    service: str,
    user_word: str,
    max_length: int,
) -> None:
    """
    Refuse a new addon whose database or user another ``addon_type`` addon owns.

    ``derive`` gives (database, user) as ``service`` stores them, ``user_word``
    is what ``service`` calls a user ("role", "user"), and ``max_length`` is
    where it cuts user names. Without the refusal, a second create would reset
    the first addon's password (and, in MySQL, grant its user the second
    database). Only a new addon (no stored secrets) is checked: refusing an
    existing one would block every redeploy of an app whose addon already works.
    """
    if load_addon_secrets(addon_type, addon_name):
        return
    other = find_identifier_clash(addon_type, addon_name, derive)
    if other is None:
        return
    db_name, db_user = derive(addon_name)
    msg = (
        f"addon name {addon_name!r} would give {service} the database "
        f"{db_name!r} and {user_word} {db_user!r}, which the existing "
        f"{addon_type} addon {other!r} already uses ('-' and '_' give the same "
        f"identifier, and {service} keeps only the first {max_length} characters "
        f"of a {user_word} name); choose another name."
    )
    raise ValueError(msg)
