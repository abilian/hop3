# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the experimental email (SMTP relay) addon."""

from __future__ import annotations

import pytest

from hop3.plugins.addons import secrets as secrets_module
from hop3.plugins.email import deliverability
from hop3.plugins.email import server_transport as server_transport_module
from hop3.plugins.email.cli import AddonEmailCreateCmd, AddonEmailStatusCmd
from hop3.plugins.email.deliverability import (
    MISSING,
    PRESENT,
    UNKNOWN,
    check_dmarc,
    check_spf,
)
from hop3.plugins.email.email import EmailAddon, EmailTransport
from hop3.plugins.email.server_transport import save_server_catch


@pytest.fixture
def email_root(tmp_path, monkeypatch):
    """Point both the addon-secrets store and the server-transport record at a
    throwaway dir, so a real server backend can't leak into a test."""
    monkeypatch.setattr(secrets_module, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(server_transport_module, "HOP3_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def no_dns(monkeypatch):
    """Stub the DNS resolver so command tests never hit the network."""
    monkeypatch.setattr(deliverability, "lookup_txt", lambda name: None)


def _configured(name: str = "mail", port: int = 587) -> EmailAddon:
    addon = EmailAddon(addon_name=name)
    addon.configure(
        EmailTransport(
            smtp_host="smtp.example.com",
            smtp_port=port,
            smtp_user="user@x",
            smtp_password="p@ss:w/rd",
            mail_from="noreply@example.com",
        )
    )
    return addon


def test_create_graceful_without_backend(email_root):
    """Email is optional: with no server backend, create() must NOT fail the
    deploy. It stores an inheriting-when-available marker and injects no SMTP
    env (surfaced, not a silent skip)."""
    addon = EmailAddon(addon_name="mail")
    addon.create()  # no raise
    stored = secrets_module.load_addon_secrets("email", "mail")
    assert stored == {"inherit": True, "pending": True}
    # No backend -> no SMTP env injected (graceful), not a fail-loud.
    assert addon.get_connection_details() == {}


def test_pending_addon_wires_email_once_a_backend_is_set(email_root, no_dns):
    """A pending addon (declared before any backend) picks the backend up on the
    next deploy — get_connection_details resolves it fresh, no re-create."""
    addon = EmailAddon(addon_name="mail")
    addon.create()  # pending (no backend yet)
    save_server_catch("dev.local")  # operator configures a backend
    env = addon.get_connection_details()  # resolves fresh
    assert env["SMTP_HOST"] == "127.0.0.1"
    assert env["DEFAULT_FROM_EMAIL"] == "noreply@dev.local"


def test_create_inherits_when_backend_configured(email_root):
    """A recipe's `[[addons]] type = "email"` (generic create) inherits the
    server backend when one is set: the addon is stored as inheriting, with its
    From on the backend's verified domain (ADR 054/056)."""
    save_server_catch("dev.local")

    EmailAddon(addon_name="bugsink-email").create()

    stored = secrets_module.load_addon_secrets("email", "bugsink-email")
    assert stored == {"inherit": True, "mail_from": "noreply@dev.local"}


def test_connection_details_emit_every_spelling(email_root):
    env = _configured().get_connection_details()
    # neutral / Node
    assert env["SMTP_HOST"] == "smtp.example.com"
    assert env["SMTP_PORT"] == "587"
    assert env["SMTP_FROM"] == "noreply@example.com"
    assert env["SMTP_TLS"] == "true"
    # Django
    assert env["EMAIL_HOST"] == "smtp.example.com"
    assert env["EMAIL_USE_TLS"] == "true"
    assert env["EMAIL_USE_SSL"] == "false"
    assert env["DEFAULT_FROM_EMAIL"] == "noreply@example.com"
    # Flask-Mail
    assert env["MAIL_SERVER"] == "smtp.example.com"
    assert env["MAIL_DEFAULT_SENDER"] == "noreply@example.com"


def test_smtp_url_percent_encodes_credentials(email_root):
    env = _configured().get_connection_details()
    # user "user@x" and password "p@ss:w/rd" must be percent-encoded in the URL
    assert env["SMTP_URL"] == "smtp://user%40x:p%40ss%3Aw%2Frd@smtp.example.com:587"


def test_implicit_tls_on_465(email_root):
    env = _configured(port=465).get_connection_details()
    assert env["SMTP_URL"].startswith("smtps://")
    assert env["EMAIL_USE_SSL"] == "true"
    assert env["EMAIL_USE_TLS"] == "false"
    assert env["SMTP_TLS"] == "false"


def test_info_never_exposes_the_password(email_root):
    info = _configured().info()
    assert info["configured"] is True
    assert info["smtp_host"] == "smtp.example.com"
    assert "smtp_password" not in info
    assert all("p@ss" not in str(v) for v in info.values())


def test_get_connection_details_unconfigured_fails_loud(email_root):
    with pytest.raises(RuntimeError, match="No SMTP transport configured"):
        EmailAddon(addon_name="nope").get_connection_details()


def test_destroy_removes_transport(email_root):
    _configured().destroy()
    assert EmailAddon(addon_name="mail").info()["configured"] is False


# ---- domain-boundary validation (EmailTransport.__post_init__) --------------


@pytest.mark.parametrize("port", [25, 2525, 0])
def test_transport_rejects_non_submission_port(port):
    with pytest.raises(ValueError, match="smtp_port must be"):
        EmailTransport("smtp.example.com", port, "u", "p", "noreply@example.com")


def test_transport_rejects_control_chars_in_from():
    # A CRLF in From could inject mail headers (Bcc, …) in a downstream app.
    with pytest.raises(ValueError, match="control characters"):
        EmailTransport("h", 587, "u", "p", "noreply@example.com\nBcc: evil@x.com")


def test_transport_rejects_bad_from():
    with pytest.raises(ValueError, match="mail_from must be an email"):
        EmailTransport("h", 587, "u", "p", "not-an-email")


def test_transport_rejects_empty_field():
    with pytest.raises(ValueError, match="must not be empty"):
        EmailTransport("h", 587, "u", "", "noreply@example.com")


# ---- CLI command layer (AddonEmailCreateCmd / AddonEmailStatusCmd) ----------


def _types(items):
    return [it["t"] for it in items]


def _joined(items):
    return " ".join(str(it.get("text", "")) for it in items)


def test_cmd_create_happy_path(email_root, no_dns):
    result = AddonEmailCreateCmd().call(
        "mail",
        "--smtp-host", "smtp.example.com",
        "--smtp-user", "u",
        "--smtp-password", "pw",
        "--from", "noreply@example.com",
    )  # fmt: skip
    assert "warning" in _types(result)  # the experimental banner
    assert "experimental" in _joined(result)
    assert EmailAddon(addon_name="mail").info()["configured"] is True


def test_cmd_create_missing_flags_is_loud(email_root):
    result = AddonEmailCreateCmd().call("mail", "--smtp-host", "smtp.example.com")
    assert "error" in _types(result)
    assert "missing" in _joined(result)
    assert EmailAddon(addon_name="mail").info()["configured"] is False


def test_cmd_create_non_int_port_is_clean_error(email_root):
    result = AddonEmailCreateCmd().call(
        "mail",
        "--smtp-host", "h", "--smtp-user", "u", "--smtp-password", "pw",
        "--from", "a@b.com", "--smtp-port", "abc",
    )  # fmt: skip
    assert "error" in _types(result)
    assert "whole number" in _joined(result)


def test_cmd_create_rejects_port_25(email_root):
    result = AddonEmailCreateCmd().call(
        "mail",
        "--smtp-host", "h", "--smtp-user", "u", "--smtp-password", "pw",
        "--from", "a@b.com", "--smtp-port", "25",
    )  # fmt: skip
    assert "error" in _types(result)
    assert "submission port" in _joined(result)
    assert EmailAddon(addon_name="mail").info()["configured"] is False


def test_cmd_status_reports_configured_and_not(email_root, no_dns):
    unconfigured = AddonEmailStatusCmd().call("mail")
    assert "warning" in _types(unconfigured)
    assert "not configured" in _joined(unconfigured)

    _configured()  # writes the 'mail' addon
    configured = AddonEmailStatusCmd().call("mail")
    assert "table" in _types(configured)
    assert "experimental" in _joined(configured)


# ---- deliverability DNS pre-flight (SPF / DMARC via dig) --------------------


def test_unquote_joins_txt_chunks():
    assert deliverability._unquote('"v=spf1 include:x ~all"') == "v=spf1 include:x ~all"
    assert deliverability._unquote('"chunk1" "chunk2"') == "chunk1chunk2"


def test_check_spf_present(monkeypatch):
    monkeypatch.setattr(
        deliverability, "lookup_txt", lambda name: ["v=spf1 include:_spf.x ~all"]
    )
    assert check_spf("example.com").status == PRESENT


def test_check_spf_missing(monkeypatch):
    monkeypatch.setattr(deliverability, "lookup_txt", lambda name: ["some-other-txt"])
    assert check_spf("example.com").status == MISSING


def test_check_dmarc_queries_underscore_name(monkeypatch):
    seen = {}

    def fake(name):
        seen["name"] = name
        return ["v=DMARC1; p=none"]

    monkeypatch.setattr(deliverability, "lookup_txt", fake)
    assert check_dmarc("example.com").status == PRESENT
    assert seen["name"] == "_dmarc.example.com"


def test_checks_unknown_when_resolver_unavailable(monkeypatch):
    monkeypatch.setattr(deliverability, "lookup_txt", lambda name: None)
    assert check_spf("example.com").status == UNKNOWN
    assert check_dmarc("example.com").status == UNKNOWN


def test_lookup_txt_none_when_dig_absent(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(deliverability.subprocess, "run", boom)
    assert deliverability.lookup_txt("example.com") is None
