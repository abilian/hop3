# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Cloud credentials managed in-app.

Credentials live in the DB (token + optional SSH key), are redacted in the UI, and
are picked up by the worker's `load_cloud_config` over env — while the env/config.toml
path stays intact as the fallback the manual `hop3-test` CLI relies on. Auth is
bypassed via TESTLAB_UNSAFE in the conftest.
"""

from __future__ import annotations

from hop3_testlab.cloud_config import load_cloud_config
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import CredentialsRepository
from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient

_FAKE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAA-not-a-real-key\n"
    "-----END OPENSSH PRIVATE KEY-----"
)


def _session():
    return get_session_factory(str(TestlabConfig.get_instance().DB_PATH))()


def test_add_credential_persists_and_is_redacted_in_the_ui(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTLAB_KEYS_DIR", str(tmp_path / "keys"))
    with TestClient(app=create_app()) as client:
        r = client.post(
            "/servers/credentials",
            data={
                "name": "hetzner-main",
                "kind": "hetzner",
                "api_token": "secret-token-xyz",
                "server_id": "115746898",
                "image": "ubuntu-24.04",
                "ssh_key_name": "deploy-key",
                "private_key": _FAKE_KEY,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        page = client.get("/servers").text

    # Stored on the row (secrets included)...
    with _session() as s:
        cred = CredentialsRepository(s).active("hetzner")
        assert cred.api_token == "secret-token-xyz"
        assert cred.server_id == 115746898
        assert cred.private_key.startswith("-----BEGIN OPENSSH PRIVATE KEY-----")

    # ...but neither secret is ever rendered.
    assert "secret-token-xyz" not in page
    assert "not-a-real-key" not in page
    assert "hetzner-main" in page
    assert "sha256:" in page  # token shown as a fingerprint


def test_cloud_config_resolves_db_credential_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTLAB_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("HETZNER_API_TOKEN", "env-token")  # must be overridden
    with _session() as s:
        CredentialsRepository(s).create(
            name="hz",
            kind="hetzner",
            api_token="db-token",
            server_id=999,
            image="ubuntu-24.04",
            ssh_key_name="k",
            private_key=_FAKE_KEY,
        )
        s.commit()

    cfg = load_cloud_config()
    assert cfg.hetzner_token == "db-token"  # DB wins over env
    assert cfg.hetzner_server_id == 999
    assert cfg.is_complete

    # The key is materialized to a 0600 file the engine subprocess can use.
    key_file = tmp_path / "keys" / "hz.key"
    assert key_file.read_text().startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert oct(key_file.stat().st_mode)[-3:] == "600"
    assert cfg.ssh_key_path == str(key_file)


def test_no_credential_row_falls_back_to_env(tmp_path, monkeypatch):
    # The manual hop3-test path: no DB credential -> env/config.toml, unchanged.
    monkeypatch.setenv("HETZNER_API_TOKEN", "env-token")
    monkeypatch.setenv("HETZNER_SERVER_ID", "42")
    cfg = load_cloud_config(tmp_path / "absent-config.toml")
    assert cfg.hetzner_token == "env-token"
    assert cfg.hetzner_server_id == 42


def test_add_credential_rejects_bad_input(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTLAB_KEYS_DIR", str(tmp_path / "keys"))
    with TestClient(app=create_app()) as client:
        # missing token
        assert (
            client.post(
                "/servers/credentials",
                data={"name": "a", "kind": "hetzner"},
                follow_redirects=False,
            ).status_code
            == 400
        )
        # non-integer server_id
        assert (
            client.post(
                "/servers/credentials",
                data={
                    "name": "b",
                    "kind": "hetzner",
                    "api_token": "t",
                    "server_id": "not-a-number",
                },
                follow_redirects=False,
            ).status_code
            == 400
        )
        # malformed private key
        assert (
            client.post(
                "/servers/credentials",
                data={
                    "name": "c",
                    "kind": "hetzner",
                    "api_token": "t",
                    "private_key": "junk",
                },
                follow_redirects=False,
            ).status_code
            == 400
        )

    with _session() as s:
        assert CredentialsRepository(s).list_all() == []  # nothing stored


def test_delete_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTLAB_KEYS_DIR", str(tmp_path / "keys"))
    with _session() as s:
        cid = (
            CredentialsRepository(s).create(name="x", kind="hetzner", api_token="t").id
        )
        s.commit()

    with TestClient(app=create_app()) as client:
        client.post(f"/servers/credentials/{cid}/delete", follow_redirects=False)

    with _session() as s:
        assert CredentialsRepository(s).get(cid) is None
