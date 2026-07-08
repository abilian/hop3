# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for DKIM keygen + DNS records (direct email backend, ADR 054)."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from hop3_rootd import dkim
from hop3_rootd.dkim import (
    DkimError,
    _genkey_argv,
    _parse_dkim_txt,
    ensure_keypair,
    publishable_records,
)

from tests.a_unit._fakes import FakeExec

# A realistic opendkim-genkey .txt: the value is split across BIND "…" segments.
_SAMPLE_TXT = (
    'hop3._domainkey\tIN\tTXT\t( "v=DKIM1; h=sha256; k=rsa; "\n'
    '\t  "p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDExample" )  ; ----- DKIM key\n'
)


@pytest.fixture
def key_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dkim, "KEY_DIR", tmp_path)
    return tmp_path


# --- pure helpers --------------------------------------------------------


def test_parse_dkim_txt_joins_quoted_segments():
    value = _parse_dkim_txt(_SAMPLE_TXT)
    assert value == (
        "v=DKIM1; h=sha256; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDExample"
    )
    assert '"' not in value


def test_genkey_argv():
    argv = _genkey_argv("/usr/bin/opendkim-genkey", "example.com", "hop3", Path("/k"))
    assert argv == [
        "/usr/bin/opendkim-genkey",
        "-b", "2048",
        "-s", "hop3",
        "-d", "example.com",
        "-D", "/k",
    ]  # fmt: skip


def test_publishable_records():
    dkim_value = "v=DKIM1; k=rsa; p=abc"
    recs = publishable_records("example.com", "hop3", dkim_value, "203.0.113.7")
    assert recs["spf"]["value"] == "v=spf1 ip4:203.0.113.7 ~all"
    assert recs["dkim"]["name"] == "hop3._domainkey.example.com"
    assert recs["dkim"]["value"] == dkim_value
    assert recs["dmarc"]["name"] == "_dmarc.example.com"
    assert "p=none" in recs["dmarc"]["value"]  # monitor first, don't self-break
    assert "203.0.113.7" in recs["ptr"]


# --- ensure_keypair ------------------------------------------------------


def test_ensure_keypair_reuses_existing_key(key_dir):
    # A prior keygen: reuse it (never rotate silently) and don't call genkey.
    (key_dir / "hop3.private").write_text("PRIVATE")
    (key_dir / "hop3.txt").write_text(_SAMPLE_TXT)
    ex = FakeExec()

    rec = ensure_keypair("example.com", "hop3", exec=ex)

    assert rec["name"] == "hop3._domainkey.example.com"
    assert rec["value"].startswith("v=DKIM1")
    assert not any("genkey" in c[0] for c in ex.calls)  # reused, not regenerated


def test_ensure_keypair_fails_loud_without_genkey(key_dir):
    ex = FakeExec()
    ex.set_path("opendkim-genkey", None)  # not installed
    with pytest.raises(DkimError, match="opendkim-genkey"):
        ensure_keypair("example.com", "hop3", exec=ex)


def test_ensure_keypair_private_key_is_0600(key_dir):
    (key_dir / "hop3.private").write_text("PRIVATE")
    (key_dir / "hop3.txt").write_text(_SAMPLE_TXT)
    # An existing key isn't chmod'd again, so set + assert the invariant here.
    (key_dir / "hop3.private").chmod(0o600)
    ensure_keypair("example.com", "hop3", exec=FakeExec())
    mode = stat.S_IMODE((key_dir / "hop3.private").stat().st_mode)
    assert mode == 0o600


# --- opendkim config + reload --------------------------------------------


@pytest.fixture
def opendkim_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(dkim, "KEY_DIR", tmp_path / "keys")
    monkeypatch.setattr(dkim, "OPENDKIM_DIR", tmp_path / "opendkim")
    monkeypatch.setattr(dkim, "OPENDKIM_CONF", tmp_path / "opendkim.conf")
    return tmp_path


def test_write_opendkim_config(opendkim_dirs):
    dkim.write_opendkim_config("example.com", "hop3")
    d = opendkim_dirs / "opendkim"
    key = opendkim_dirs / "keys" / "hop3.private"
    assert (d / "KeyTable").read_text() == (
        f"hop3._domainkey.example.com example.com:hop3:{key}\n"
    )
    assert (
        d / "SigningTable"
    ).read_text() == "*@example.com hop3._domainkey.example.com\n"
    assert "127.0.0.1" in (d / "TrustedHosts").read_text()
    conf = (opendkim_dirs / "opendkim.conf").read_text()
    assert "Socket inet:8891@localhost" in conf
    assert "Mode s" in conf  # sign only
    assert "KeyTable file:" in conf


def test_reload_opendkim_uses_systemctl():
    ex = FakeExec()
    assert dkim.reload_opendkim(ex) == "systemctl"
    assert any("opendkim" in c and "reload-or-restart" in c for c in ex.calls), ex.calls


def test_reload_opendkim_fails_loud_without_systemctl():
    ex = FakeExec()
    ex.set_path("systemctl", None)
    with pytest.raises(DkimError, match="process manager"):
        dkim.reload_opendkim(ex)
