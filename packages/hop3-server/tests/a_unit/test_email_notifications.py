# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for platform notifications (M3.1 feature 5).

Covers the SMTP sender (STARTTLS vs implicit TLS), the opt-in config, the
best-effort `notify` delivery (fail-loud-but-never-raise), the
`server email notifications` CLI, and the cert-renewal-failure wiring.
"""

from __future__ import annotations

import stat
from types import SimpleNamespace
from typing import ClassVar

import pytest

from hop3.plugins.email import (
    notifications as notif_module,
    sender as sender_module,
    server_transport as st_module,
)
from hop3.plugins.email.email import EmailTransport
from hop3.plugins.email.notifications import (
    load_notifications_config,
    notification_recipient,
    notifications_enabled,
    notify,
    save_notifications_config,
)
from hop3.plugins.email.notify_cli import ServerEmailNotificationsCmd
from hop3.plugins.email.sender import send_via_transport
from hop3.plugins.email.server_transport import save_server_transport
from hop3.server import cert_renewal_service as crs_module


@pytest.fixture
def notif_root(tmp_path, monkeypatch):
    """Point the server-transport + notifications stores at a throwaway dir."""
    monkeypatch.setattr(st_module, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(notif_module, "HOP3_ROOT", tmp_path)
    return tmp_path


class _RecordingSMTP:
    """A context-manager fake for smtplib.SMTP / SMTP_SSL."""

    instances: ClassVar[list] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.actions: list = []
        _RecordingSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.actions.append("starttls")

    def login(self, user, password):
        self.actions.append(("login", user, password))

    def send_message(self, msg):
        self.actions.append(("send", msg["To"], msg["Subject"], msg["From"]))


@pytest.fixture
def fake_smtp(monkeypatch):
    _RecordingSMTP.instances = []
    monkeypatch.setattr(sender_module.smtplib, "SMTP", _RecordingSMTP)
    monkeypatch.setattr(sender_module.smtplib, "SMTP_SSL", _RecordingSMTP)
    return _RecordingSMTP


def _transport(port: int = 587) -> EmailTransport:
    return EmailTransport("smtp.example.com", port, "user", "pw", "noreply@example.com")


def _admin_repo():
    return SimpleNamespace(get_by_username=lambda u: SimpleNamespace(is_admin=True))


def _nonadmin_repo():
    return SimpleNamespace(get_by_username=lambda u: SimpleNamespace(is_admin=False))


def _types(items):
    return [it["t"] for it in items]


def _joined(items):
    return " ".join(str(it.get("text", "")) for it in items)


# ---- SMTP sender ------------------------------------------------------------


def test_send_via_transport_uses_starttls_on_587(fake_smtp):
    send_via_transport(_transport(587), "to@x.com", "Sub", "Body")
    inst = fake_smtp.instances[-1]
    assert inst.port == 587
    assert "starttls" in inst.actions
    assert ("login", "user", "pw") in inst.actions
    assert any(
        a[0] == "send" and a[1] == "to@x.com" and a[2] == "Sub" for a in inst.actions
    )


def test_send_via_transport_implicit_tls_on_465_no_starttls(fake_smtp):
    send_via_transport(_transport(465), "to@x.com", "Sub", "Body")
    inst = fake_smtp.instances[-1]
    assert inst.port == 465
    assert "starttls" not in inst.actions  # implicit TLS — STARTTLS would error
    assert ("login", "user", "pw") in inst.actions


def test_send_via_transport_sets_from_to_transport_sender(fake_smtp):
    send_via_transport(_transport(), "to@x.com", "Sub", "Body")
    send_action = next(a for a in fake_smtp.instances[-1].actions if a[0] == "send")
    assert send_action[3] == "noreply@example.com"  # From = the transport's sender


# ---- opt-in config ----------------------------------------------------------


def test_config_default_disabled(notif_root):
    assert load_notifications_config() == {"enabled": False}
    assert notifications_enabled() is False


def test_config_round_trip(notif_root):
    save_notifications_config(enabled=True, recipient="ops@x.com")
    assert notifications_enabled() is True
    assert load_notifications_config()["recipient"] == "ops@x.com"


def test_config_file_is_0600(notif_root):
    save_notifications_config(enabled=True)
    path = notif_module._store_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_recipient_override_wins(notif_root, monkeypatch):
    monkeypatch.setattr(
        notif_module, "config", SimpleNamespace(ACME_EMAIL="acme@x.com")
    )
    save_notifications_config(enabled=True, recipient="override@x.com")
    assert notification_recipient() == "override@x.com"


def test_recipient_falls_back_to_acme_email(notif_root, monkeypatch):
    monkeypatch.setattr(
        notif_module, "config", SimpleNamespace(ACME_EMAIL="acme@x.com")
    )
    save_notifications_config(enabled=True)  # no explicit recipient
    assert notification_recipient() == "acme@x.com"


def test_recipient_empty_when_nothing_set(notif_root, monkeypatch):
    monkeypatch.setattr(notif_module, "config", SimpleNamespace(ACME_EMAIL=""))
    assert notification_recipient() == ""


# ---- notify() delivery (best-effort, fail-loud-but-never-raise) -------------


def test_notify_disabled_is_a_noop(notif_root, monkeypatch):
    called = {}
    monkeypatch.setattr(
        notif_module, "send_via_transport", lambda *a: called.setdefault("sent", True)
    )
    assert notify("e", "s", "b") is False
    assert "sent" not in called


def test_notify_enabled_sends_via_transport(notif_root, monkeypatch):
    sent = {}
    monkeypatch.setattr(
        notif_module,
        "send_via_transport",
        lambda t, r, s, b: sent.update(to=r, subj=s, body=b),
    )
    save_server_transport(_transport())
    save_notifications_config(enabled=True, recipient="ops@x.com")
    assert notify("cert-renewal-failure", "Subj", "Body") is True
    assert sent == {"to": "ops@x.com", "subj": "Subj", "body": "Body"}


def test_notify_enabled_without_transport_returns_false_no_send(
    notif_root, monkeypatch
):
    called = {}
    monkeypatch.setattr(
        notif_module, "send_via_transport", lambda *a: called.setdefault("sent", True)
    )
    save_notifications_config(enabled=True, recipient="ops@x.com")  # but no transport
    assert notify("e", "s", "b") is False
    assert "sent" not in called  # never attempted a send


def test_notify_enabled_without_recipient_returns_false(notif_root, monkeypatch):
    monkeypatch.setattr(notif_module, "config", SimpleNamespace(ACME_EMAIL=""))
    called = {}
    monkeypatch.setattr(
        notif_module, "send_via_transport", lambda *a: called.setdefault("sent", True)
    )
    save_server_transport(_transport())
    save_notifications_config(enabled=True)  # no recipient, no ACME email
    assert notify("e", "s", "b") is False
    assert "sent" not in called


def test_notify_swallows_send_failure_but_returns_false(notif_root, monkeypatch):
    def boom(*a):
        msg = "smtp down"
        raise RuntimeError(msg)

    monkeypatch.setattr(notif_module, "send_via_transport", boom)
    save_server_transport(_transport())
    save_notifications_config(enabled=True, recipient="ops@x.com")
    # A delivery failure must NOT propagate (it can't break the reporting op)...
    assert notify("e", "s", "b") is False  # ...but is reported as not-sent


def test_notify_survives_corrupt_notifications_store(notif_root):
    # A corrupt / partially-written config must not make notify() raise — the
    # cert-renewal cycle that calls it relies on the "never raises" contract.
    path = notif_module._store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json")
    assert notify("e", "s", "b") is False


def test_notify_survives_invalid_stored_transport(notif_root):
    # A hand-edited transport (bad port) is rejected by EmailTransport; notify()
    # must surface it and return False, not raise.
    save_notifications_config(enabled=True, recipient="ops@x.com")
    tpath = st_module._store_path()
    tpath.parent.mkdir(parents=True, exist_ok=True)
    tpath.write_text(
        '{"smtp_host":"h","smtp_port":25,"smtp_user":"u",'
        '"smtp_password":"p","mail_from":"a@b.com"}'
    )
    assert notify("e", "s", "b") is False


# ---- CLI: server email notifications <on|off|status|test> -------------------


def test_cli_on_without_transport_warns(notif_root, monkeypatch):
    monkeypatch.setattr(notif_module, "config", SimpleNamespace(ACME_EMAIL=""))
    result = ServerEmailNotificationsCmd(user_repo=_admin_repo()).call(
        "admin", "on", "--to", "ops@x.com"
    )
    assert "will NOT send" in _joined(result)
    assert notifications_enabled() is True  # opt-in still recorded


def test_cli_on_with_transport_shows_recipient(notif_root):
    save_server_transport(_transport())
    result = ServerEmailNotificationsCmd(user_repo=_admin_repo()).call(
        "admin", "on", "--to", "ops@x.com"
    )
    assert "ops@x.com" in _joined(result)
    assert "will NOT send" not in _joined(result)


def test_cli_off_disables(notif_root):
    save_notifications_config(enabled=True)
    ServerEmailNotificationsCmd(user_repo=_admin_repo()).call("admin", "off")
    assert notifications_enabled() is False


def test_cli_status_warns_when_on_but_undeliverable(notif_root, monkeypatch):
    monkeypatch.setattr(notif_module, "config", SimpleNamespace(ACME_EMAIL=""))
    save_notifications_config(enabled=True, recipient="ops@x.com")  # no transport
    result = ServerEmailNotificationsCmd(user_repo=_admin_repo()).call(
        "admin", "status"
    )
    assert "not deliverable" in _joined(result)


def test_cli_test_sends_a_message(notif_root, fake_smtp):
    save_server_transport(_transport())
    result = ServerEmailNotificationsCmd(user_repo=_admin_repo()).call(
        "admin", "test", "--to", "ops@x.com"
    )
    assert "error" not in _types(result)
    assert fake_smtp.instances  # a real send happened
    assert "ops@x.com" in _joined(result)


def test_cli_test_without_transport_fails_loud(notif_root):
    result = ServerEmailNotificationsCmd(user_repo=_admin_repo()).call(
        "admin", "test", "--to", "ops@x.com"
    )
    assert "error" in _types(result)
    assert "No server email transport" in _joined(result)


def test_cli_unknown_action_is_loud(notif_root):
    result = ServerEmailNotificationsCmd(user_repo=_admin_repo()).call("admin", "bogus")
    assert "error" in _types(result)
    assert "unknown action" in _joined(result)


def test_cli_requires_admin(notif_root):
    result = ServerEmailNotificationsCmd(user_repo=_nonadmin_repo()).call(
        "bob", "status"
    )
    assert "error" in _types(result)
    assert "Admin privileges required" in _joined(result)


# ---- cert-renewal-failure wiring --------------------------------------------


def test_notify_renewal_failures_batches_into_one_notify(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "hop3.plugins.email.notifications.notify",
        lambda ev, sub, body: seen.update(ev=ev, sub=sub, body=body) or True,
    )
    crs_module._notify_renewal_failures([
        ("a.example.com", "acme timeout"),
        ("b", "dns"),
    ])
    assert seen["ev"] == "cert-renewal-failure"
    assert "2 certificate" in seen["sub"]
    assert "a.example.com" in seen["body"]
    assert "b" in seen["body"]
