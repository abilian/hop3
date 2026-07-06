# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Server-level shared email transport (EXPERIMENTAL).

The operator sets the SMTP submission credentials once, at the server level;
per-app email addons created without their own ``--smtp-*`` inherit them (see
:func:`resolve_inherited`). This is the transport foundation the local relay and
provider profiles build on (``release-plan-0.7`` M3.1).

The record is a singleton, stored root-owned at
``HOP3_ROOT/server/email-transport.json`` with ``0600`` permissions — a
server-config location, deliberately *not* under ``addons/email/`` so it never
shows up as a phantom addon instance in ``hop3 addon list``.

Encryption at rest is deferred platform-wide (M3.8): the file is ``0600``
root-owned, the same posture as every other addon secret today
(postgres/mysql/s3), so the SMTP password is protected by file permissions, not
yet by a key.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from hop3.config import HOP3_ROOT

from .email import EmailTransport

if TYPE_CHECKING:
    from pathlib import Path


def _store_path() -> Path:
    """Path to the singleton server-transport record.

    Computed at call time (not bound at import) so a test can point
    ``HOP3_ROOT`` at a throwaway dir — the same seam the addon-secrets store
    uses.
    """
    return HOP3_ROOT / "server" / "email-transport.json"


def save_server_transport(
    transport: EmailTransport, dkim_selector: str | None = None
) -> None:
    """Store (or rotate) the server-level transport. Idempotent.

    ``dkim_selector`` (when known, from a provider profile or an explicit
    ``--dkim-selector``) is recorded so ``server email status`` can re-verify
    DKIM later.
    """
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    record: dict[str, object] = {
        "smtp_host": transport.smtp_host,
        "smtp_port": transport.smtp_port,
        "smtp_user": transport.smtp_user,
        "smtp_password": transport.smtp_password,
        "mail_from": transport.mail_from,
    }
    if dkim_selector:
        record["dkim_selector"] = dkim_selector
    path.write_text(json.dumps(record, indent=2))
    path.chmod(0o600)


def load_server_dkim_selector() -> str | None:
    """The DKIM selector recorded with the server transport, if any."""
    path = _store_path()
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("dkim_selector")


def load_server_transport() -> EmailTransport | None:
    """Load the server-level transport, or None when it is unset."""
    path = _store_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return EmailTransport(
        smtp_host=data["smtp_host"],
        smtp_port=int(data["smtp_port"]),
        smtp_user=data["smtp_user"],
        smtp_password=data["smtp_password"],
        mail_from=data["mail_from"],
    )


def resolve_inherited(mail_from: str) -> EmailTransport:
    """The effective transport for an app that inherits the server transport.

    Loads the server-level transport and swaps in the app's own From address.
    Fails loud when no server transport is set, or when ``mail_from`` is not on
    the server's verified sending domain — an app must not send as an
    unverified domain through the shared transport.
    """
    server = load_server_transport()
    if server is None:
        msg = (
            "No server email transport is configured. Set one with "
            "`hop3 server email set --smtp-host <h> --smtp-user <u> "
            "--smtp-password <pw> --from-domain <domain>`, or pass "
            "--smtp-host/--smtp-user/--smtp-password for a per-app transport."
        )
        raise RuntimeError(msg)

    # Construct with the app's From first, so EmailTransport validates its
    # shape/control-chars before the domain-boundary check below.
    transport = EmailTransport(
        smtp_host=server.smtp_host,
        smtp_port=server.smtp_port,
        smtp_user=server.smtp_user,
        smtp_password=server.smtp_password,
        mail_from=mail_from,
    )
    server_domain = server.mail_from.split("@")[-1].lower()
    app_domain = transport.mail_from.split("@")[-1].lower()
    if app_domain != server_domain:
        msg = (
            f"From address {mail_from!r} is not on the server's verified sending "
            f"domain {server_domain!r}. Use an address on {server_domain}, or pass "
            "--smtp-host/--smtp-user/--smtp-password for a per-app transport."
        )
        raise RuntimeError(msg)
    return transport
