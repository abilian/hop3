# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Administrative commands that act across the whole Hop3 install.

These commands are admin-only (gated via ``require_admin``) and are
typically run once during maintenance windows rather than in everyday
CLI flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hop3.core.credentials import SCHEME_V2_PREFIX, get_credential_encryptor
from hop3.lib.registry import register

# Repositories are runtime imports for Dishka DI (not just type hints)
from hop3.orm.repositories import (  # ruff:ignore[typing-only-first-party-import]
    AddonCredentialRepository,
    UserRepository,
)

from ._base import Command
from ._response import summary, text
from .user import require_admin


@register
@dataclass(frozen=True)
class AdminReencryptCredentialsCmd(Command):
    """Rewrite stored addon credentials under the current (v2) scheme.

    Usage:
        hop3 admin reencrypt-credentials [--dry-run]

    Decrypts every AddonCredential row (auto-detecting v1 vs v2) and
    rewrites it at the current scheme. Safe to run repeatedly --- rows
    already at v2 are skipped. Pass --dry-run to see what would change
    without touching the database.

    Examples:
        hop3 admin reencrypt-credentials
        hop3 admin reencrypt-credentials --dry-run
    """

    addon_credential_repo: AddonCredentialRepository
    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("admin", "reencrypt-credentials")
    # ADR 036 D3: `admin` is off the user-visible surface (still runnable).
    hidden: ClassVar[bool] = True
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", *args: str) -> list[dict]:
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        dry_run = "--dry-run" in args
        encryptor = get_credential_encryptor()

        all_credentials = list(self.addon_credential_repo.get_many())
        already_v2 = 0
        migrated = 0
        failures: list[str] = []

        for credential in all_credentials:
            record = credential.encrypted_data
            if record.startswith(SCHEME_V2_PREFIX):
                already_v2 += 1
                continue
            try:
                plaintext = encryptor.decrypt(record)
            except Exception as e:
                failures.append(
                    f"  ! credential id={credential.id} "
                    f"(app_id={credential.app_id}, addon={credential.addon_type}"
                    f"/{credential.addon_name}): {e}"
                )
                continue
            if not dry_run:
                credential.encrypted_data = encryptor.encrypt(plaintext)
            migrated += 1

        if not dry_run and migrated:
            self.addon_credential_repo.session.commit()

        verb = "would re-encrypt" if dry_run else "re-encrypted"
        lines: list[dict] = [
            text(f"Addon credentials scanned: {len(all_credentials)}"),
            text(f"  Already v2: {already_v2}"),
            text(f"  {verb.capitalize()}: {migrated}"),
        ]
        if failures:
            lines.append(text(f"  Failed to decrypt: {len(failures)}"))
            lines.extend(text(msg) for msg in failures)

        lines.append(
            summary(
                f"{verb} {migrated} credential(s) "
                f"({already_v2} already at v2, {len(failures)} failed)."
            )
        )
        return lines
