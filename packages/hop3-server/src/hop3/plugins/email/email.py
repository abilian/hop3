# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Email (SMTP relay) addon — EXPERIMENTAL.

``EmailAddon`` implements the ``Addon`` protocol but provisions no server-side
resource: it stores the operator's upstream SMTP submission credentials and
renders them as env vars for attached apps. Because no two frameworks read the
same names, :func:`_connection_vars` emits one transport under every common
spelling — neutral ``SMTP_*`` + an ``SMTP_URL``, Django ``EMAIL_*``, and
Flask-Mail ``MAIL_*`` — the same multi-alias precedent the S3 addon sets with
its ``S3_*``/``AWS_*`` aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from hop3.plugins.addons.secrets import (
    delete_addon_secrets,
    load_addon_secrets,
    save_addon_secrets,
)

if TYPE_CHECKING:
    from pathlib import Path

_TYPE = "email"

# Submission ports only: 587 (STARTTLS) or 465 (implicit TLS). Port 25 is
# loopback-only and blocked outbound on the cloud, so it is not a valid
# submission target here (a local relay on 25 is a separate, deferred feature).
STARTTLS_PORT = 587
IMPLICIT_TLS_PORT = 465
SUBMISSION_PORTS = (STARTTLS_PORT, IMPLICIT_TLS_PORT)


def _has_control_chars(value: str) -> bool:
    """True if the string holds an ASCII control char (CR/LF/tab/…/DEL).

    A control char in a host/user/password/From can break the env-file
    serialization or inject SMTP/email headers in a downstream app, so it is
    refused at the boundary.
    """
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in value)


def _looks_like_email(value: str) -> bool:
    """Cheap sanity check on a From address — a full RFC 5322 validator is
    overkill; this only rejects an obviously-wrong address before storing it."""
    if value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    return bool(local) and "." in domain


@dataclass(frozen=True, slots=True)
class EmailTransport:
    """The operator's upstream SMTP submission credentials + default From.

    Validation lives here, at the domain boundary — not only in the CLI — so no
    path (a direct call, a hand-edited secrets file, a future declarative
    `[[addons]]` path) can store a plaintext/forgeable transport.
    """

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    mail_from: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("smtp_host", self.smtp_host),
            ("smtp_user", self.smtp_user),
            ("smtp_password", self.smtp_password),
            ("mail_from", self.mail_from),
        ):
            if not value:
                msg = f"{field_name} must not be empty"
                raise ValueError(msg)
            if _has_control_chars(value):
                msg = f"{field_name} must not contain control characters"
                raise ValueError(msg)
        if self.smtp_port not in SUBMISSION_PORTS:
            msg = (
                f"smtp_port must be {STARTTLS_PORT} (STARTTLS) or "
                f"{IMPLICIT_TLS_PORT} (implicit TLS), not {self.smtp_port}; "
                "port 25 is not a submission port on the cloud"
            )
            raise ValueError(msg)
        if not _looks_like_email(self.mail_from):
            msg = f"mail_from must be an email address, got {self.mail_from!r}"
            raise ValueError(msg)

    @property
    def use_starttls(self) -> bool:
        return self.smtp_port == STARTTLS_PORT

    @property
    def use_implicit_tls(self) -> bool:
        return self.smtp_port == IMPLICIT_TLS_PORT


@dataclass(frozen=True)
class EmailAddon:
    """SMTP-relay addon implementing the Addon protocol (experimental).

    One instance per ``addon email create <name> …``. There is nothing to
    provision on a server — the addon stores the operator's upstream transport
    and renders it as env vars for attached apps.
    """

    name: str = _TYPE
    addon_name: str = ""

    def __post_init__(self) -> None:
        if not self.addon_name:
            msg = "addon_name is required for EmailAddon"
            raise ValueError(msg)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def configure(self, transport: EmailTransport) -> None:
        """Store (or replace) the upstream transport for this addon.

        Idempotent: re-running with new credentials rotates them in place. This
        is what ``addon email create`` calls — the generic ``addon create email``
        path has no transport to store and fails loud (see :meth:`create`).
        """
        save_addon_secrets(
            _TYPE,
            self.addon_name,
            {
                "smtp_host": transport.smtp_host,
                "smtp_port": transport.smtp_port,
                "smtp_user": transport.smtp_user,
                "smtp_password": transport.smtp_password,
                "mail_from": transport.mail_from,
            },
        )

    def create(self) -> None:
        """Generic-create guard — always refuses.

        The generic ``addon create <type> <name>`` path cannot supply or validate
        the SMTP credentials an email addon needs, so it is never a valid way to
        create one — configured or not. Fail loud and point at the typed command,
        rather than let the generic path silently no-op over an already-stored
        transport (Hop3's no-fake-success rule). The real entry point is
        ``addon email create``, which calls :meth:`configure`.
        """
        msg = (
            f"Email addon {self.addon_name!r} needs SMTP credentials the generic "
            "`addon create` cannot supply. Create it with:\n"
            f"  hop3 addon email create {self.addon_name} "
            "--smtp-host <h> --smtp-user <u> --smtp-password <pw> --from <addr>"
        )
        raise RuntimeError(msg)

    def destroy(self) -> None:
        """Remove the stored transport. Idempotent."""
        delete_addon_secrets(_TYPE, self.addon_name)

    # ------------------------------------------------------------------
    # Connection details (env var injection)
    # ------------------------------------------------------------------

    def get_connection_details(self) -> dict[str, str]:
        """Render the transport as env vars under every common spelling."""
        transport = self._load_transport()
        if transport is None:
            msg = (
                f"No SMTP transport configured for email addon {self.addon_name!r}. "
                f"Run: hop3 addon email create {self.addon_name} --smtp-host <h> …"
            )
            raise RuntimeError(msg)
        return _connection_vars(transport)

    # ------------------------------------------------------------------
    # Backup / restore — an email relay stores no data of its own
    # ------------------------------------------------------------------

    def backup(self) -> Path:
        msg = (
            "Email addon has no data to back up — it only holds the operator's "
            f"SMTP credentials. Re-create it with: hop3 addon email create "
            f"{self.addon_name} --smtp-host <h> …"
        )
        raise RuntimeError(msg)

    def restore(self, backup_path: Path) -> None:
        msg = (
            "Email addon cannot be restored from a backup — re-create it with: "
            f"hop3 addon email create {self.addon_name} --smtp-host <h> …"
        )
        raise RuntimeError(msg)

    def info(self) -> dict[str, Any]:
        """Status for `hop3 addon email status` — never includes the password."""
        transport = self._load_transport()
        if transport is None:
            return {"addon_name": self.addon_name, "type": _TYPE, "configured": False}
        return {
            "addon_name": self.addon_name,
            "type": _TYPE,
            "configured": True,
            "smtp_host": transport.smtp_host,
            "smtp_port": str(transport.smtp_port),
            "mail_from": transport.mail_from,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_transport(self) -> EmailTransport | None:
        data = load_addon_secrets(_TYPE, self.addon_name)
        if data is None:
            return None
        return EmailTransport(
            smtp_host=data["smtp_host"],
            smtp_port=int(data["smtp_port"]),
            smtp_user=data["smtp_user"],
            smtp_password=data["smtp_password"],
            mail_from=data["mail_from"],
        )


def _connection_vars(t: EmailTransport) -> dict[str, str]:
    """One transport, every common spelling (neutral + Django + Flask)."""
    port = str(t.smtp_port)
    tls = "true" if t.use_starttls else "false"
    ssl = "true" if t.use_implicit_tls else "false"
    scheme = "smtps" if t.use_implicit_tls else "smtp"
    url = (
        f"{scheme}://{quote(t.smtp_user, safe='')}:"
        f"{quote(t.smtp_password, safe='')}@{t.smtp_host}:{t.smtp_port}"
    )
    return {
        # Neutral / Node / nodemailer
        "SMTP_HOST": t.smtp_host,
        "SMTP_PORT": port,
        "SMTP_USER": t.smtp_user,
        "SMTP_PASSWORD": t.smtp_password,
        "SMTP_FROM": t.mail_from,
        "SMTP_TLS": tls,
        "SMTP_URL": url,
        # Django (django.core.mail)
        "EMAIL_HOST": t.smtp_host,
        "EMAIL_PORT": port,
        "EMAIL_HOST_USER": t.smtp_user,
        "EMAIL_HOST_PASSWORD": t.smtp_password,
        "EMAIL_USE_TLS": tls,
        "EMAIL_USE_SSL": ssl,
        "DEFAULT_FROM_EMAIL": t.mail_from,
        # Flask-Mail
        "MAIL_SERVER": t.smtp_host,
        "MAIL_PORT": port,
        "MAIL_USERNAME": t.smtp_user,
        "MAIL_PASSWORD": t.smtp_password,
        "MAIL_USE_TLS": tls,
        "MAIL_USE_SSL": ssl,
        "MAIL_DEFAULT_SENDER": t.mail_from,
    }
