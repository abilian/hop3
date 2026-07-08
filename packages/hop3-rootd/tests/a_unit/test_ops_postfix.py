# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the loopback Postfix relay helper + op (ADR 054)."""

from __future__ import annotations

import stat

import pytest
from hop3_rootd import PROTOCOL_VERSION, postfix as pf
from hop3_rootd.ops import get_handler
from hop3_rootd.ops._base import OpContext, OpHandler
from hop3_rootd.postfix import PostfixError, PostfixUnavailableError
from hop3_rootd.protocol import Request
from hop3_rootd.state import State
from hop3_rootd.validation import ValidationError

from tests.a_unit._fakes import FakeExec, SaveSpy, fail


@pytest.fixture
def postfix_dir(tmp_path, monkeypatch):
    """Point POSTFIX_DIR at a tmp dir so no real /etc/postfix is touched."""
    monkeypatch.setattr(pf, "POSTFIX_DIR", tmp_path)
    return tmp_path


def _ran(ex: FakeExec, binary: str) -> bool:
    return any(call and call[0].endswith(binary) for call in ex.calls)


# --- helper: configure ---------------------------------------------------


def test_configure_writes_nullclient(postfix_dir):
    ex = FakeExec()
    result = pf.configure(
        "smtp.example.com", 587, sasl_user="user", sasl_password="pw", exec=ex
    )

    main = (postfix_dir / "main.cf").read_text()
    assert "inet_interfaces = loopback-only" in main
    assert "relayhost = [smtp.example.com]:587" in main
    assert "smtpd_relay_restrictions = permit_mynetworks, reject" in main
    assert "smtp_sasl_auth_enable = yes" in main
    assert "smtp_tls_security_level = encrypt" in main
    assert "smtp_tls_wrappermode" not in main  # 587 is STARTTLS, not implicit TLS

    sasl = postfix_dir / "sasl_passwd"
    assert sasl.read_text() == "[smtp.example.com]:587 user:pw\n"
    assert stat.S_IMODE(sasl.stat().st_mode) == 0o600  # secret is not world-readable

    assert _ran(ex, "postmap")
    assert _ran(ex, "systemctl")
    assert result["relayhost"] == "[smtp.example.com]:587"
    assert "pw" not in str(result)  # never echo the password


def test_configure_465_uses_wrapper_tls(postfix_dir):
    pf.configure(
        "smtp.example.com", 465, sasl_user="u", sasl_password="pw", exec=FakeExec()
    )
    assert "smtp_tls_wrappermode = yes" in (postfix_dir / "main.cf").read_text()


def test_configure_catch_no_sasl_no_tls(postfix_dir):
    # A dev sink: relay plaintext to Mailpit, no SASL, no map, no postmap.
    ex = FakeExec()
    result = pf.configure("127.0.0.1", 1025, use_tls=False, exec=ex)
    main = (postfix_dir / "main.cf").read_text()
    assert "relayhost = [127.0.0.1]:1025" in main
    assert "smtp_sasl_auth_enable = no" in main
    assert "smtp_tls_security_level = none" in main
    assert not (postfix_dir / "sasl_passwd").exists()  # no credential map for a sink
    assert not _ran(ex, "postmap")
    assert _ran(ex, "systemctl")
    assert result["relayhost"] == "[127.0.0.1]:1025"


def test_configure_missing_postmap_fails_before_writing(postfix_dir):
    ex = FakeExec()
    ex.set_path("postmap", None)
    with pytest.raises(PostfixUnavailableError, match="postmap"):
        pf.configure(
            "smtp.example.com", 587, sasl_user="u", sasl_password="pw", exec=ex
        )
    assert not (postfix_dir / "main.cf").exists()  # aborted before any write


def test_configure_postmap_failure_is_loud(postfix_dir):
    ex = FakeExec().on(lambda a: bool(a) and a[0].endswith("postmap"), fail("bad map"))
    with pytest.raises(PostfixError, match="postmap"):
        pf.configure(
            "smtp.example.com", 587, sasl_user="u", sasl_password="pw", exec=ex
        )


def test_configure_no_reload_method_fails_loud(postfix_dir):
    ex = FakeExec()
    ex.set_path("systemctl", None)
    ex.set_path("postfix", None)
    with pytest.raises(PostfixUnavailableError, match="reload"):
        pf.configure(
            "smtp.example.com", 587, sasl_user="u", sasl_password="pw", exec=ex
        )


def test_reload_starts_postfix_when_stopped(postfix_dir):
    # No systemd (supervisor container): `postfix status` stopped -> `postfix start`.
    ex = FakeExec()
    ex.set_path("systemctl", None)
    ex.on(
        lambda a: bool(a) and a[0].endswith("postfix") and "status" in a,
        fail("not running"),
    )
    result = pf.configure("127.0.0.1", 1025, use_tls=False, exec=ex)
    assert any(a[0].endswith("postfix") and "start" in a for a in ex.calls)
    assert result["reloaded"] == "postfix start"


def test_reload_falls_back_to_postfix_when_systemctl_fails(postfix_dir):
    # systemctl present but systemd not booted -> fall back; postfix running -> reload.
    ex = FakeExec()
    ex.on(
        lambda a: bool(a) and a[0].endswith("systemctl"),
        fail("System has not been booted with systemd"),
    )
    result = pf.configure("127.0.0.1", 1025, use_tls=False, exec=ex)
    assert result["reloaded"] == "postfix reload"


# --- op: postfix.configure -----------------------------------------------


def _handler() -> OpHandler:
    handler = get_handler("postfix.configure")
    assert handler is not None, "postfix.configure not registered"
    return handler


def _ctx(ex: FakeExec) -> OpContext:
    return OpContext(
        state=State(),
        save_state=SaveSpy(),
        now_iso=lambda: "2026-07-08T00:00:00+00:00",
        new_rule_id=lambda: "r1",
        exec=ex,
    )


def _req(**args) -> Request:
    return Request(v=PROTOCOL_VERSION, id="req-1", op="postfix.configure", args=args)


def test_op_rejects_port_25(postfix_dir):
    with pytest.raises(ValidationError):
        _handler()(
            _req(
                relay_host="smtp.example.com",
                relay_port=25,
                sasl_user="u",
                sasl_password="pw",
            ),
            _ctx(FakeExec()),
        )


def test_op_rejects_control_char_in_password(postfix_dir):
    # A newline in the password would inject a second sasl_passwd line.
    with pytest.raises(ValidationError):
        _handler()(
            _req(
                relay_host="smtp.example.com",
                relay_port=587,
                sasl_user="u",
                sasl_password="p\nw",
            ),
            _ctx(FakeExec()),
        )


def test_op_result_omits_password(postfix_dir):
    result = _handler()(
        _req(
            relay_host="smtp.example.com",
            relay_port=587,
            sasl_user="user",
            sasl_password="s3cret",
        ),
        _ctx(FakeExec()),
    )
    assert "s3cret" not in str(result)
    assert result["relay_host"] == "smtp.example.com"


def test_op_catch_mode(postfix_dir):
    result = _handler()(_req(mode="catch"), _ctx(FakeExec()))
    assert result["mode"] == "catch"
    assert result["relayhost"] == "[127.0.0.1]:1025"


def test_op_unknown_mode_is_loud(postfix_dir):
    with pytest.raises(ValidationError):
        _handler()(_req(mode="bogus"), _ctx(FakeExec()))
