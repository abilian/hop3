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

from hop3.lib import log
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


def validate_mail_from(mail_from: str) -> None:
    """Raise ``ValueError`` if a From is empty, malformed, or holds control chars.

    Shared by ``EmailTransport`` and the credential-less catch backend so both
    enforce the same From-boundary check (no header injection, no forged sender).
    """
    if not mail_from:
        msg = "mail_from must not be empty"
        raise ValueError(msg)
    if _has_control_chars(mail_from):
        msg = "mail_from must not contain control characters"
        raise ValueError(msg)
    if not _looks_like_email(mail_from):
        msg = f"mail_from must be an email address, got {mail_from!r}"
        raise ValueError(msg)


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

    def configure_inherited(self, mail_from: str) -> None:
        """Store this addon as inheriting the server-level transport.

        Only the app's own From address is kept; the SMTP credentials are
        resolved from the server transport at attach time (see
        :func:`server_transport.resolve_inherited`), so rotating the server
        transport propagates here without re-creating the addon.
        """
        save_addon_secrets(
            _TYPE, self.addon_name, {"inherit": True, "mail_from": mail_from}
        )

    def create(self) -> None:
        """Provision from the server backend if one is set; otherwise stay inert.

        This is the path a recipe's ``[[addons]] type = "email"`` takes. Email is
        an OPTIONAL enhancement — the app runs fine without it — so a missing
        server backend must not fail the deploy. When a backend (relay/catch/
        direct) is configured, the addon inherits it: the app's From is placed on
        the backend's verified sending domain and it sends via the loopback relay
        (ADR 054/056). When none is configured, the addon is stored as
        inheriting-when-available and a loud, actionable notice is surfaced — the
        app runs without outbound email until the operator sets a backend, after
        which a redeploy wires it (the backend is resolved fresh in
        :meth:`get_connection_details`). This is a surfaced degradation of an
        optional feature, not a silent skip.
        """
        from .server_transport import (  # ruff:ignore[import-outside-top-level]
            server_sending_domain,
        )

        domain = server_sending_domain()
        if domain is not None:
            self.configure_inherited(f"noreply@{domain}")
            return

        save_addon_secrets(_TYPE, self.addon_name, {"inherit": True, "pending": True})
        log(
            f"  email addon {self.addon_name!r}: no server email backend is "
            "configured — this app will run WITHOUT outbound email. Enable it "
            "with `hop3 server email backend <catch|relay|direct> …`, then "
            "redeploy to wire it.",
            level=0,
            fg="yellow",
        )

    def destroy(self) -> None:
        """Remove the stored transport. Idempotent."""
        delete_addon_secrets(_TYPE, self.addon_name)

    # ------------------------------------------------------------------
    # Connection details (env var injection)
    # ------------------------------------------------------------------

    def get_connection_details(self) -> dict[str, str]:
        """Render the app's SMTP env vars under every common spelling.

        An **inheriting** addon points the app at the loopback relay
        (``127.0.0.1:25``, ADR 054): the app speaks SMTP to the local Postfix,
        which relays to the active backend using credentials held only in
        Postfix — the provider password never enters the app's environment.
        Resolving the server transport still fails loud if the backend is gone.

        An addon with its **own** ``--smtp-*`` provider (an override) injects
        that provider's endpoint directly.
        """
        data = load_addon_secrets(_TYPE, self.addon_name)
        if data is None:
            msg = (
                f"No SMTP transport configured for email addon {self.addon_name!r}. "
                f"Run: hop3 addon email create {self.addon_name} --smtp-host <h> …"
            )
            raise RuntimeError(msg)
        if data.get("inherit"):
            # Inheriting apps send via the loopback relay regardless of backend
            # kind (relay/catch/direct). Resolve the backend FRESH each deploy, so
            # configuring one later + redeploying wires email with no re-create.
            from .server_transport import (  # ruff:ignore[import-outside-top-level]
                assert_inherited_backend,
                server_sending_domain,
            )

            domain = server_sending_domain()
            if domain is None:
                # No backend (yet): email stays off. Surfaced, not hidden — the
                # app gets no SMTP env and shows its own "email not set up" state
                # honestly. Configure a backend + redeploy to enable.
                log(
                    f"  email addon {self.addon_name!r}: no server email backend; "
                    "injecting no SMTP env (set one + redeploy to enable email).",
                    level=1,
                    fg="yellow",
                )
                return {}
            mail_from = data.get("mail_from") or f"noreply@{domain}"
            assert_inherited_backend(mail_from)
            return _loopback_vars(mail_from)
        transport = self._load_transport()
        assert transport is not None
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
        data = load_addon_secrets(_TYPE, self.addon_name)
        if data is None:
            return {"addon_name": self.addon_name, "type": _TYPE, "configured": False}
        if data.get("inherit"):
            return self._inherited_info(data["mail_from"])

        transport = self._load_transport()
        assert transport is not None  # data present ⇒ a transport
        return {
            "addon_name": self.addon_name,
            "type": _TYPE,
            "configured": True,
            "inherited": False,
            "smtp_host": transport.smtp_host,
            "smtp_port": str(transport.smtp_port),
            "mail_from": transport.mail_from,
        }

    def _inherited_info(self, mail_from: str) -> dict[str, Any]:
        """Status for an inheriting addon — kind-aware, never a fake relay.

        A relay backend shows the resolved server host; a catch (or other
        loopback) backend shows ``127.0.0.1:25``, since the app sends there. A
        backend that is no longer set surfaces the fail-loud error.
        """
        from .server_transport import (  # ruff:ignore[import-outside-top-level]
            RELAY_BACKEND,
            assert_inherited_backend,
            load_server_backend_kind,
            resolve_inherited,
        )

        base = {
            "addon_name": self.addon_name,
            "type": _TYPE,
            "configured": True,
            "inherited": True,
            "mail_from": mail_from,
        }
        try:
            assert_inherited_backend(mail_from)
        except RuntimeError as exc:
            return {**base, "error": str(exc)}
        if load_server_backend_kind() == RELAY_BACKEND:
            transport = resolve_inherited(mail_from)
            return {
                **base,
                "smtp_host": transport.smtp_host,
                "smtp_port": str(transport.smtp_port),
            }
        # catch / direct: the app sends via the loopback relay.
        return {**base, "smtp_host": _LOOPBACK_HOST, "smtp_port": _LOOPBACK_PORT}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_transport(self) -> EmailTransport | None:
        data = load_addon_secrets(_TYPE, self.addon_name)
        if data is None:
            return None
        if data.get("inherit"):
            # Resolve against the server-level transport at read time, so
            # rotating the server transport propagates to every inheriting app.
            # Raises (fail-loud) if the server transport is no longer set.
            from .server_transport import (  # ruff:ignore[import-outside-top-level]
                resolve_inherited,
            )

            return resolve_inherited(data["mail_from"])
        return EmailTransport(
            smtp_host=data["smtp_host"],
            smtp_port=int(data["smtp_port"]),
            smtp_user=data["smtp_user"],
            smtp_password=data["smtp_password"],
            mail_from=data["mail_from"],
        )


_LOOPBACK_HOST = "127.0.0.1"
_LOOPBACK_PORT = "25"


def _loopback_vars(mail_from: str) -> dict[str, str]:
    """Env vars pointing an inheriting app at the local loopback relay.

    The app sends to ``127.0.0.1:25`` with no auth; the Hop3-managed Postfix
    relays to the active backend (ADR 054). No provider credential is emitted —
    it lives only in Postfix. Every common spelling points at the loopback.
    """
    host, port = _LOOPBACK_HOST, _LOOPBACK_PORT
    url = f"smtp://{host}:{port}"
    return {
        # Neutral / Node / nodemailer
        "SMTP_HOST": host,
        "SMTP_PORT": port,
        "SMTP_USER": "",
        "SMTP_PASSWORD": "",
        "SMTP_FROM": mail_from,
        "SMTP_TLS": "false",
        "SMTP_URL": url,
        # Django (django.core.mail)
        "EMAIL_HOST": host,
        "EMAIL_PORT": port,
        "EMAIL_HOST_USER": "",
        "EMAIL_HOST_PASSWORD": "",
        "EMAIL_USE_TLS": "false",
        "EMAIL_USE_SSL": "false",
        "DEFAULT_FROM_EMAIL": mail_from,
        # Flask-Mail
        "MAIL_SERVER": host,
        "MAIL_PORT": port,
        "MAIL_USERNAME": "",
        "MAIL_PASSWORD": "",
        "MAIL_USE_TLS": "false",
        "MAIL_USE_SSL": "false",
        "MAIL_DEFAULT_SENDER": mail_from,
    }


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
