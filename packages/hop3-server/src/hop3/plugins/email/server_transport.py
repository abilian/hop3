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

from .email import EmailTransport, validate_mail_from

if TYPE_CHECKING:
    from pathlib import Path

# Backend kinds stored in the record's ``backend`` key. A record written before
# this key existed is a relay (back-compat).
RELAY_BACKEND = "relay"
CATCH_BACKEND = "catch"

_NO_BACKEND_MSG = (
    "No server email transport is configured. Set one with "
    "`hop3 server email backend <relay|catch|direct> …` (relay: --smtp-host / "
    "--smtp-user / --smtp-password / --from-domain), or pass "
    "--smtp-host/--smtp-user/--smtp-password for a per-app transport."
)


def _store_path() -> Path:
    """Path to the singleton server-backend record.

    Computed at call time (not bound at import) so a test can point
    ``HOP3_ROOT`` at a throwaway dir — the same seam the addon-secrets store
    uses.
    """
    return HOP3_ROOT / "server" / "email-transport.json"


def _load_record() -> dict | None:
    path = _store_path()
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _write_record(record: dict) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(record, indent=2))
    path.chmod(0o600)


def save_server_transport(
    transport: EmailTransport, dkim_selector: str | None = None
) -> None:
    """Store (or rotate) the server-level relay transport. Idempotent.

    ``dkim_selector`` (when known, from a provider profile or an explicit
    ``--dkim-selector``) is recorded so ``server email status`` can re-verify
    DKIM later.
    """
    record: dict[str, object] = {
        "backend": RELAY_BACKEND,
        "smtp_host": transport.smtp_host,
        "smtp_port": transport.smtp_port,
        "smtp_user": transport.smtp_user,
        "smtp_password": transport.smtp_password,
        "mail_from": transport.mail_from,
    }
    if dkim_selector:
        record["dkim_selector"] = dkim_selector
    _write_record(record)


def save_server_catch(from_domain: str) -> None:
    """Store the dev-catch backend (mail captured, never sent).

    No provider credentials — the loopback Postfix relays to a local Mailpit.
    Only a from-domain is kept, for the inherit From-boundary check.
    """
    _write_record({"backend": CATCH_BACKEND, "mail_from": f"noreply@{from_domain}"})


def load_server_backend_kind() -> str | None:
    """The active backend kind (``relay`` | ``catch`` | …), or None when unset.

    A record without a ``backend`` key predates the field and is a relay.
    """
    data = _load_record()
    return None if data is None else data.get("backend", RELAY_BACKEND)


def load_server_dkim_selector() -> str | None:
    """The DKIM selector recorded with the server transport, if any."""
    data = _load_record()
    return None if data is None else data.get("dkim_selector")


def load_server_transport() -> EmailTransport | None:
    """Load the server relay transport, or None when unset / not a relay backend."""
    data = _load_record()
    if data is None or data.get("backend", RELAY_BACKEND) != RELAY_BACKEND:
        return None
    return EmailTransport(
        smtp_host=data["smtp_host"],
        smtp_port=int(data["smtp_port"]),
        smtp_user=data["smtp_user"],
        smtp_password=data["smtp_password"],
        mail_from=data["mail_from"],
    )


def assert_inherited_backend(mail_from: str) -> None:
    """Validate that an app may inherit the active backend.

    Backend-agnostic: an inheriting app always sends via the loopback relay, so
    it needs no provider transport — only that a backend is set and ``mail_from``
    is well-formed and on the backend's verified sending domain. Fails loud
    otherwise (the message names the missing backend, like the relay path).
    """
    data = _load_record()
    if data is None:
        raise RuntimeError(_NO_BACKEND_MSG)
    try:
        validate_mail_from(mail_from)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    server_domain = str(data["mail_from"]).split("@")[-1].lower()
    app_domain = mail_from.rsplit("@", maxsplit=1)[-1].lower()
    if app_domain != server_domain:
        msg = (
            f"From address {mail_from!r} is not on the server's verified sending "
            f"domain {server_domain!r}. Use an address on {server_domain}, or pass "
            "--smtp-host/--smtp-user/--smtp-password for a per-app transport."
        )
        raise RuntimeError(msg)


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
