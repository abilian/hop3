# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""generate_with_certbot's command construction + cert install.

Exercises the certbot code path (the part that regresses) without a live ACME
server: a stubbed ``shell`` captures the certbot invocation and writes the live
cert files, so we verify the ``--server`` flag (pebble / LE-staging), the
ACME_WWW webroot (the edrix.eu fix), ``--force-renewal``, and that the issued
cert lands in the key store. A real handshake against pebble is a CI-infra
follow-up, enabled by the ACME_SERVER config exercised here.
"""

from __future__ import annotations

import pytest

from hop3.platform import certificates
from hop3.platform.certificates import Certificate

DOMAIN = "app.example.com"


@pytest.fixture
def certbot_env(tmp_path, monkeypatch):
    """Point cert dirs at a throwaway tree and capture the certbot command."""
    monkeypatch.setattr(certificates, "KEY_STORE", tmp_path / "certs")
    monkeypatch.setattr(certificates, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(certificates, "ACME_WWW", tmp_path / "acme")
    monkeypatch.setattr(certificates, "NGINX_ROOT", tmp_path / "nginx")
    monkeypatch.setattr(certificates, "ACME_EMAIL", "ops@example.com")
    (tmp_path / "certs").mkdir()
    (tmp_path / "nginx").mkdir()

    captured: dict[str, str] = {}

    def fake_shell(cmd):
        captured["cmd"] = cmd
        live = tmp_path / "certbot" / "config" / "live" / DOMAIN
        live.mkdir(parents=True, exist_ok=True)
        (live / "fullchain.pem").write_text("LIVE-CERT")
        (live / "privkey.pem").write_text("LIVE-KEY")

    monkeypatch.setattr(certificates, "shell", fake_shell)
    return captured


def test_certbot_command_includes_acme_server_and_installs(certbot_env, monkeypatch):
    monkeypatch.setattr(certificates, "ACME_SERVER", "https://pebble:14000/dir")

    cert = Certificate(DOMAIN)
    cert.generate_with_certbot(force=True)

    cmd = certbot_env["cmd"]
    assert "certbot certonly --webroot -w" in cmd
    assert str(certificates.ACME_WWW) in cmd  # webroot == ACME_WWW (edrix fix)
    assert f"-d {DOMAIN}" in cmd
    assert "--server https://pebble:14000/dir" in cmd
    assert "--force-renewal" in cmd
    # The issued cert is copied into the key store.
    assert cert.get_crt() == "LIVE-CERT"
    assert cert.get_key() == "LIVE-KEY"


def test_certbot_command_omits_server_by_default(certbot_env, monkeypatch):
    monkeypatch.setattr(certificates, "ACME_SERVER", "")

    Certificate(DOMAIN).generate_with_certbot(force=False)

    assert "--server" not in certbot_env["cmd"]
