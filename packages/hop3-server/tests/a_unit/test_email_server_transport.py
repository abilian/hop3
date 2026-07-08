# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the server-level shared email transport (M3.1 feature 1).

Covers the store (`server_transport`), the inherit resolution (server creds +
app's own From, domain-boundary), the admin-gated `server email set/status`
commands, and the inherit-vs-override path in `addon email create`.
"""

from __future__ import annotations

import stat
from types import SimpleNamespace

import pytest

from hop3.plugins.addons import secrets as secrets_module
from hop3.plugins.email import deliverability, providers, server_transport as st_module
from hop3.plugins.email.cli import AddonEmailCreateCmd, AddonEmailStatusCmd
from hop3.plugins.email.email import EmailAddon, EmailTransport
from hop3.plugins.email.server_cli import (
    ServerEmailBackendCmd,
    ServerEmailSetCmd,
    ServerEmailStatusCmd,
)
from hop3.plugins.email.server_transport import (
    load_server_dkim_selector,
    load_server_transport,
    resolve_inherited,
    save_server_transport,
)


@pytest.fixture
def email_root(tmp_path, monkeypatch):
    """Point both the addon-secrets store and the server-transport store at a
    throwaway dir."""
    monkeypatch.setattr(secrets_module, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(st_module, "HOP3_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def no_dns(monkeypatch):
    """Stub the DNS resolver so command tests never hit the network."""
    monkeypatch.setattr(deliverability, "lookup_txt", lambda name: None)


def _server_transport(domain: str = "example.com") -> EmailTransport:
    return EmailTransport(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="relay-user",
        smtp_password="s3cr3t",
        mail_from=f"noreply@{domain}",
    )


def _admin_repo():
    return SimpleNamespace(
        get_by_username=lambda u: SimpleNamespace(is_admin=True, username=u)
    )


def _nonadmin_repo():
    return SimpleNamespace(
        get_by_username=lambda u: SimpleNamespace(is_admin=False, username=u)
    )


def _types(items):
    return [it["t"] for it in items]


def _joined(items):
    return " ".join(str(it.get("text", "")) for it in items)


# ---- store round-trip -------------------------------------------------------


def test_save_load_round_trip(email_root):
    save_server_transport(_server_transport())
    loaded = load_server_transport()
    assert loaded is not None
    assert loaded.smtp_host == "smtp.example.com"
    assert loaded.smtp_port == 587
    assert loaded.smtp_user == "relay-user"
    assert loaded.smtp_password == "s3cr3t"
    assert loaded.mail_from == "noreply@example.com"


def test_load_none_when_unset(email_root):
    assert load_server_transport() is None


def test_store_file_is_0600(email_root):
    save_server_transport(_server_transport())
    path = st_module._store_path()
    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_store_lives_outside_addons_dir(email_root):
    # The singleton must never appear as a phantom addon instance in `addon list`.
    save_server_transport(_server_transport())
    assert (email_root / "server" / "email-transport.json").exists()
    assert not (email_root / "addons" / "email").exists()


# ---- resolve_inherited ------------------------------------------------------


def test_resolve_inherited_uses_server_creds_with_app_from(email_root):
    save_server_transport(_server_transport())
    t = resolve_inherited("team@example.com")
    assert t.smtp_host == "smtp.example.com"
    assert t.smtp_user == "relay-user"
    assert t.smtp_password == "s3cr3t"
    assert t.mail_from == "team@example.com"  # the app's own From


def test_resolve_inherited_fails_loud_without_server_transport(email_root):
    with pytest.raises(RuntimeError, match="No server email transport"):
        resolve_inherited("team@example.com")


def test_resolve_inherited_rejects_off_domain_from(email_root):
    save_server_transport(_server_transport("example.com"))
    with pytest.raises(RuntimeError, match="verified sending domain"):
        resolve_inherited("team@evil.com")


def test_resolve_inherited_rejects_subdomain(email_root):
    # A subdomain is a distinct sending identity for SPF/DKIM — refuse it.
    save_server_transport(_server_transport("example.com"))
    with pytest.raises(RuntimeError, match="verified sending domain"):
        resolve_inherited("team@mail.example.com")


# ---- server email set (admin-gated) -----------------------------------------


def test_set_requires_admin(email_root, no_dns):
    result = ServerEmailSetCmd(user_repo=_nonadmin_repo()).call(
        "bob",
        "--smtp-host", "smtp.example.com", "--smtp-user", "u",
        "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert "error" in _types(result)
    assert "Admin privileges required" in _joined(result)
    assert load_server_transport() is None  # nothing stored


def test_set_stores_transport_for_admin(email_root, no_dns):
    result = ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--smtp-host", "smtp.example.com", "--smtp-user", "u",
        "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert "warning" in _types(result)  # the experimental banner
    assert "experimental" in _joined(result)
    loaded = load_server_transport()
    assert loaded is not None
    assert loaded.smtp_host == "smtp.example.com"
    assert loaded.mail_from == "noreply@example.com"


def test_set_rejects_from_domain_with_at(email_root):
    result = ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--smtp-host", "h", "--smtp-user", "u",
        "--smtp-password", "pw", "--from-domain", "noreply@example.com",
    )  # fmt: skip
    assert "error" in _types(result)
    assert "bare domain" in _joined(result)
    assert load_server_transport() is None


def test_set_rejects_port_25(email_root):
    result = ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--smtp-host", "h", "--smtp-user", "u",
        "--smtp-password", "pw", "--from-domain", "example.com",
        "--smtp-port", "25",
    )  # fmt: skip
    assert "error" in _types(result)
    assert "submission port" in _joined(result)


def test_set_missing_flags_is_loud(email_root):
    result = ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin", "--smtp-host", "smtp.example.com"
    )
    assert "error" in _types(result)
    assert "missing" in _joined(result)
    assert load_server_transport() is None


# ---- server email status ----------------------------------------------------


def test_status_not_configured(email_root):
    result = ServerEmailStatusCmd(user_repo=_admin_repo()).call("admin")
    assert "warning" in _types(result)
    assert "No server email transport" in _joined(result)


def test_status_shows_transport_never_password(email_root, no_dns):
    save_server_transport(_server_transport())
    result = ServerEmailStatusCmd(user_repo=_admin_repo()).call("admin")
    assert "table" in _types(result)
    table_item = next(it for it in result if it["t"] == "table")
    flat = " ".join(" ".join(map(str, row)) for row in table_item["rows"])
    assert "smtp.example.com" in flat
    assert "example.com" in flat
    assert "s3cr3t" not in flat  # never the password


def test_status_requires_admin(email_root):
    result = ServerEmailStatusCmd(user_repo=_nonadmin_repo()).call("bob")
    assert "error" in _types(result)
    assert "Admin privileges required" in _joined(result)


# ---- addon email create: inherit vs override --------------------------------


def test_create_inherits_server_transport(email_root, no_dns):
    save_server_transport(_server_transport())
    result = AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    assert "error" not in _types(result)
    info = EmailAddon(addon_name="mail").info()
    assert info["configured"] is True
    assert info["inherited"] is True
    assert info["smtp_host"] == "smtp.example.com"  # resolved from the server
    assert info["mail_from"] == "team@example.com"


def test_create_inherit_injects_loopback_relay(email_root, no_dns):
    # An inheriting app sends via the loopback relay (ADR 054); the server
    # creds live in Postfix, never in app env. Only the app's From is injected.
    save_server_transport(_server_transport())
    AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    env = EmailAddon(addon_name="mail").get_connection_details()
    assert env["SMTP_HOST"] == "127.0.0.1"
    assert env["SMTP_PORT"] == "25"
    assert env["SMTP_USER"] == ""  # no provider cred in app env
    assert env["SMTP_PASSWORD"] == ""
    assert env["SMTP_FROM"] == "team@example.com"
    assert "s3cr3t" not in str(env)  # the server password never leaks to the app


def test_create_inherit_fails_loud_without_server_transport(email_root, no_dns):
    result = AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    assert "error" in _types(result)
    assert "No server email transport" in _joined(result)
    assert EmailAddon(addon_name="mail").info()["configured"] is False


def test_create_inherit_rejects_off_domain(email_root, no_dns):
    save_server_transport(_server_transport("example.com"))
    result = AddonEmailCreateCmd().call("mail", "--from", "team@evil.com")
    assert "error" in _types(result)
    assert "verified sending domain" in _joined(result)
    assert EmailAddon(addon_name="mail").info()["configured"] is False


def test_create_partial_smtp_is_refused(email_root, no_dns):
    save_server_transport(_server_transport())
    # host without user/password -> override path -> all three become required.
    result = AddonEmailCreateCmd().call(
        "mail", "--from", "team@example.com", "--smtp-host", "smtp.own.com"
    )
    assert "error" in _types(result)
    joined = _joined(result)
    assert "missing" in joined
    assert "--smtp-user" in joined
    assert "--smtp-password" in joined
    assert EmailAddon(addon_name="mail").info()["configured"] is False


def test_create_own_transport_overrides_server(email_root, no_dns):
    save_server_transport(_server_transport())  # a server transport exists
    result = AddonEmailCreateCmd().call(
        "mail",
        "--from", "noreply@own.com",
        "--smtp-host", "smtp.own.com", "--smtp-user", "own",
        "--smtp-password", "pw",
    )  # fmt: skip
    assert "error" not in _types(result)
    info = EmailAddon(addon_name="mail").info()
    assert info["inherited"] is False
    assert info["smtp_host"] == "smtp.own.com"  # own creds, not the server's
    assert info["mail_from"] == "noreply@own.com"  # own domain, not the server's


# ---- inherited addon whose server transport later disappears ----------------


def test_inherited_info_surfaces_missing_server_transport(email_root):
    save_server_transport(_server_transport())
    AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    # Server transport deleted out from under the inheriting addon.
    st_module._store_path().unlink()
    info = EmailAddon(addon_name="mail").info()
    assert info["configured"] is True
    assert info["inherited"] is True
    assert "No server email transport" in info["error"]


def test_inherited_connection_details_fail_loud_when_server_gone(email_root):
    save_server_transport(_server_transport())
    AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    st_module._store_path().unlink()
    with pytest.raises(RuntimeError, match="No server email transport"):
        EmailAddon(addon_name="mail").get_connection_details()


def test_status_inherited_surfaces_error_when_server_gone(email_root, no_dns):
    # `addon email status` on an inheriting addon whose server transport is gone
    # must surface the fail-loud message, not crash on the absent fields.
    save_server_transport(_server_transport())
    AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    st_module._store_path().unlink()
    result = AddonEmailStatusCmd().call("mail")
    assert "error" in _types(result)
    assert "No server email transport" in _joined(result)


def test_create_explicit_port_on_inherit_path_fails_loud(email_root, no_dns):
    # An explicit --smtp-port signals a per-app transport, so it must not be
    # silently dropped onto the inherit path (which uses the server's port).
    save_server_transport(_server_transport())  # server on 587
    result = AddonEmailCreateCmd().call(
        "mail", "--from", "team@example.com", "--smtp-port", "465"
    )
    assert "error" in _types(result)
    joined = _joined(result)
    assert "missing" in joined
    assert "--smtp-host" in joined  # tells the user what a per-app transport needs
    assert EmailAddon(addon_name="mail").info()["configured"] is False


# ---- DKIM auto-verify (deliverability.check_dkim + selector storage) ---------


def _dns_map(mapping):
    """A lookup_txt stub keyed on the queried name (None = no resolver)."""
    return mapping.get


def _dns_all_present(domain="example.com", selector="sel"):
    return _dns_map({
        domain: [f"v=spf1 include:_spf.{domain} ~all"],
        f"_dmarc.{domain}": ["v=DMARC1; p=none"],
        f"{selector}._domainkey.{domain}": ["v=DKIM1; k=rsa; p=MIGfMA0..."],
    })


def _dkim_row(result):
    """The DKIM row of the last table in a command result."""
    tables = [it for it in result if it["t"] == "table"]
    return next(r for r in tables[-1]["rows"] if r[1] == "DKIM")


def test_check_dkim_present_with_public_key(monkeypatch):
    monkeypatch.setattr(
        deliverability,
        "lookup_txt",
        _dns_map({"sel._domainkey.example.com": ["v=DKIM1; k=rsa; p=MIGf..."]}),
    )
    assert (
        deliverability.check_dkim("example.com", "sel").status == deliverability.PRESENT
    )


def test_check_dkim_present_without_v_tag(monkeypatch):
    # A DKIM record's defining field is p= (v=DKIM1 is optional).
    monkeypatch.setattr(
        deliverability,
        "lookup_txt",
        _dns_map({"sel._domainkey.example.com": ["k=rsa; p=MIGf..."]}),
    )
    assert (
        deliverability.check_dkim("example.com", "sel").status == deliverability.PRESENT
    )


def test_check_dkim_queries_selector_domainkey_name(monkeypatch):
    seen = {}

    def fake(name):
        seen["name"] = name
        return ["p=abc"]

    monkeypatch.setattr(deliverability, "lookup_txt", fake)
    deliverability.check_dkim("example.com", "brevo1")
    assert seen["name"] == "brevo1._domainkey.example.com"


def test_check_dkim_missing_when_no_record(monkeypatch):
    monkeypatch.setattr(deliverability, "lookup_txt", lambda name: [])
    assert (
        deliverability.check_dkim("example.com", "sel").status == deliverability.MISSING
    )


def test_check_dkim_unknown_when_resolver_unavailable(monkeypatch):
    monkeypatch.setattr(deliverability, "lookup_txt", lambda name: None)
    assert (
        deliverability.check_dkim("example.com", "sel").status == deliverability.UNKNOWN
    )


def test_server_dkim_selector_round_trip(email_root):
    save_server_transport(_server_transport(), dkim_selector="resend")
    assert load_server_dkim_selector() == "resend"


def test_server_dkim_selector_none_when_unset(email_root):
    save_server_transport(_server_transport())  # no selector passed
    assert load_server_dkim_selector() is None


def test_server_dkim_selector_none_when_no_transport(email_root):
    assert load_server_dkim_selector() is None


def test_status_reverifies_dkim_with_stored_selector(email_root, monkeypatch):
    save_server_transport(_server_transport(), dkim_selector="sel")
    monkeypatch.setattr(deliverability, "lookup_txt", _dns_all_present())
    result = ServerEmailStatusCmd(user_repo=_admin_repo()).call("admin")
    # the selector shows in the config table
    config_table = next(it for it in result if it["t"] == "table")
    flat = " ".join(" ".join(map(str, row)) for row in config_table["rows"])
    assert "sel" in flat
    # and the deliverability table carries a real (checked) DKIM row, not "—"
    assert _dkim_row(result)[0] == "✓"


def test_inherit_create_shows_dkim_when_server_has_selector(email_root, monkeypatch):
    save_server_transport(_server_transport(), dkim_selector="sel")
    monkeypatch.setattr(deliverability, "lookup_txt", _dns_all_present())
    result = AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    assert _dkim_row(result)[0] == "✓"


def test_own_transport_create_keeps_dkim_guidance_row(email_root, no_dns):
    # A per-app own transport has no known selector -> DKIM stays a guidance row.
    result = AddonEmailCreateCmd().call(
        "mail",
        "--from", "noreply@own.com",
        "--smtp-host", "smtp.own.com", "--smtp-user", "u", "--smtp-password", "pw",
    )  # fmt: skip
    assert _dkim_row(result)[0] == "—"


def test_status_inherited_addon_shows_real_dkim_row(email_root, monkeypatch):
    # `addon email status` on an inherited addon uses the server's DKIM selector
    # (consistent with create + `server email status`), not a stale guidance row.
    monkeypatch.setattr(deliverability, "lookup_txt", _dns_all_present())
    save_server_transport(_server_transport(), dkim_selector="sel")
    AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    result = AddonEmailStatusCmd().call("mail")
    assert _dkim_row(result)[0] == "✓"


def test_status_own_transport_keeps_dkim_guidance_row(email_root, no_dns):
    # A per-app own transport has no domain-level selector -> guidance row in status.
    AddonEmailCreateCmd().call(
        "mail",
        "--from", "noreply@own.com",
        "--smtp-host", "smtp.own.com", "--smtp-user", "u", "--smtp-password", "pw",
    )  # fmt: skip
    result = AddonEmailStatusCmd().call("mail")
    assert _dkim_row(result)[0] == "—"


# ---- provider profiles (providers.py + `server email set --provider`) --------


def test_get_provider_is_case_insensitive():
    assert providers.get_provider("BREVO").smtp_host == "smtp-relay.brevo.com"
    assert providers.get_provider("  Mailgun-EU ").smtp_host == "smtp.eu.mailgun.org"
    assert providers.get_provider("nonesuch") is None


def test_only_resend_has_a_fixed_dkim_selector():
    # Per the provider docs: only Resend exposes a fixed, guessable selector.
    assert providers.get_provider("resend").dkim_selector == "resend"
    for name in ("postmark", "brevo", "mailgun", "mailgun-eu", "scaleway"):
        assert providers.get_provider(name).dkim_selector == "", name


def test_list_providers_lists_the_roster(email_root):
    result = ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin", "--list-providers"
    )
    prov_table = next(it for it in result if it["t"] == "table")
    names = [row[0] for row in prov_table["rows"]]
    assert names == ["resend", "postmark", "brevo", "mailgun", "mailgun-eu", "scaleway"]


def test_list_providers_requires_admin(email_root):
    result = ServerEmailSetCmd(user_repo=_nonadmin_repo()).call(
        "bob", "--list-providers"
    )
    assert "error" in _types(result)
    assert "Admin privileges required" in _joined(result)


def test_set_provider_fills_endpoint_and_shows_spf(email_root, no_dns):
    result = ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--provider", "brevo",
        "--smtp-user", "u", "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert "error" not in _types(result)
    loaded = load_server_transport()
    assert loaded.smtp_host == "smtp-relay.brevo.com"
    assert loaded.smtp_port == 587
    assert "spf.brevo.com" in _joined(result)  # the publish-this SPF hint
    assert load_server_dkim_selector() is None  # brevo is per-account


def test_set_provider_resend_supplies_fixed_dkim_selector(email_root, no_dns):
    ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--provider", "resend",
        "--smtp-user", "resend", "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert load_server_dkim_selector() == "resend"


def test_set_unknown_provider_fails_loud(email_root):
    result = ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--provider", "nope",
        "--smtp-user", "u", "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert "error" in _types(result)
    assert "unknown provider" in _joined(result)
    assert load_server_transport() is None


def test_set_provider_with_explicit_host_conflicts(email_root):
    result = ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--provider", "brevo", "--smtp-host", "smtp.other.com",
        "--smtp-user", "u", "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert "error" in _types(result)
    assert "already sets" in _joined(result)
    assert load_server_transport() is None


def test_set_provider_with_explicit_port_conflicts(email_root):
    result = ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--provider", "brevo", "--smtp-port", "465",
        "--smtp-user", "u", "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert "error" in _types(result)
    assert "already sets" in _joined(result)


def test_set_explicit_dkim_selector_overrides_provider(email_root, no_dns):
    ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--provider", "resend", "--dkim-selector", "custom",
        "--smtp-user", "r", "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert load_server_dkim_selector() == "custom"  # explicit wins over resend's


def test_set_dkim_selector_without_provider(email_root, no_dns):
    ServerEmailSetCmd(user_repo=_admin_repo()).call(
        "admin",
        "--smtp-host", "smtp.own.com",
        "--smtp-user", "u", "--smtp-password", "pw", "--from-domain", "example.com",
        "--dkim-selector", "s1",
    )  # fmt: skip
    assert load_server_dkim_selector() == "s1"


# ---- server email backend <kind> (admin-gated) ------------------------------


def test_backend_relay_stores_transport(email_root, no_dns):
    # `backend relay` is the canonical spelling of `server email set`.
    result = ServerEmailBackendCmd(user_repo=_admin_repo()).call(
        "admin", "relay",
        "--smtp-host", "smtp.example.com", "--smtp-user", "u",
        "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert "experimental" in _joined(result)
    loaded = load_server_transport()
    assert loaded is not None
    assert loaded.smtp_host == "smtp.example.com"


def test_backend_relay_requires_admin(email_root, no_dns):
    result = ServerEmailBackendCmd(user_repo=_nonadmin_repo()).call(
        "bob", "relay",
        "--smtp-host", "smtp.example.com", "--smtp-user", "u",
        "--smtp-password", "pw", "--from-domain", "example.com",
    )  # fmt: skip
    assert "error" in _types(result)
    assert "Admin privileges required" in _joined(result)
    assert load_server_transport() is None


def test_backend_catch_selects_dev_sink(email_root):
    result = ServerEmailBackendCmd(user_repo=_admin_repo()).call(
        "admin", "catch", "--from-domain", "example.com"
    )
    assert "error" not in _types(result)
    assert "captured, not sent" in _joined(result)
    assert st_module.load_server_backend_kind() == "catch"
    assert load_server_transport() is None  # a sink has no provider transport


def test_backend_catch_requires_admin(email_root):
    result = ServerEmailBackendCmd(user_repo=_nonadmin_repo()).call("bob", "catch")
    assert "error" in _types(result)
    assert "Admin privileges required" in _joined(result)
    assert st_module.load_server_backend_kind() is None


def test_backend_catch_inherited_addon_injects_loopback(email_root, no_dns):
    # Under catch, an inheriting app still gets the loopback endpoint (:25);
    # Postfix relays to the sink. No provider transport is needed.
    ServerEmailBackendCmd(user_repo=_admin_repo()).call(
        "admin", "catch", "--from-domain", "example.com"
    )
    result = AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    assert "error" not in _types(result)
    env = EmailAddon(addon_name="mail").get_connection_details()
    assert env["SMTP_HOST"] == "127.0.0.1"
    assert env["SMTP_PORT"] == "25"
    info = EmailAddon(addon_name="mail").info()
    assert info["inherited"] is True
    assert info["smtp_host"] == "127.0.0.1"


def test_backend_direct_selects_self_hosted_mta(email_root, no_dns):
    result = ServerEmailBackendCmd(user_repo=_admin_repo()).call(
        "admin", "direct", "--from-domain", "example.com", "--server-ip", "203.0.113.7"
    )
    assert "error" not in _types(result)
    assert "direct" in _joined(result)
    assert st_module.load_server_backend_kind() == "direct"
    assert st_module.load_server_dkim_selector() == "hop3"  # default selector stored


def test_backend_direct_requires_from_domain(email_root):
    result = ServerEmailBackendCmd(user_repo=_admin_repo()).call("admin", "direct")
    assert "error" in _types(result)
    assert "from-domain" in _joined(result)
    assert st_module.load_server_backend_kind() is None


def test_backend_direct_inherited_addon_injects_loopback(email_root, no_dns):
    # A direct-backed inheriting app also sends via the loopback (:25); Postfix
    # then delivers to MX. No provider transport needed.
    ServerEmailBackendCmd(user_repo=_admin_repo()).call(
        "admin", "direct", "--from-domain", "example.com", "--server-ip", "203.0.113.7"
    )
    AddonEmailCreateCmd().call("mail", "--from", "team@example.com")
    env = EmailAddon(addon_name="mail").get_connection_details()
    assert env["SMTP_HOST"] == "127.0.0.1"
    assert env["SMTP_PORT"] == "25"


def test_backend_unknown_kind_is_loud(email_root):
    result = ServerEmailBackendCmd(user_repo=_admin_repo()).call("admin", "smtp")
    assert "error" in _types(result)
    assert "unknown backend" in _joined(result)


def test_backend_missing_kind_shows_usage(email_root):
    result = ServerEmailBackendCmd(user_repo=_admin_repo()).call("admin")
    assert "error" in _types(result)
    assert "backend <relay|catch|direct>" in _joined(result)
