# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
App admin-credential bootstrap (ADR 056).

Provision generates the password once and injects the canonical HOP3_ADMIN_*
vars; the credential is stored encrypted and retrievable; reset rotates it; and
the post-deploy create command runs exactly once and fails loud.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from hop3.deployers import admin_bootstrap
from hop3.deployers.admin_bootstrap import (
    AdminBootstrapError,
    bootstrap_admin_account,
    format_admin_credential,
    provision_admin_credential,
    read_admin_credential,
    resolve_admin_email,
    surface_admin_credential,
)
from hop3.deployers.deployer import _bootstrap_admin_account
from hop3.deployers.env_provisioning import set_env_vars
from hop3.orm import App

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture
def operator(monkeypatch):
    """Pin OPERATOR_EMAIL for the module's email resolution."""
    monkeypatch.setattr(
        admin_bootstrap, "config", SimpleNamespace(OPERATOR_EMAIL="op@example.com")
    )


def _app(session: Session, name: str = "wiki") -> App:
    app = App(name=name)
    session.add(app)
    session.flush()
    return app


def _env(app: App) -> dict[str, str]:
    return {ev.name: ev.value for ev in app.env_vars}


def test_provision_generates_stores_and_injects(db_session, operator):
    app = _app(db_session)
    admin = {
        "username": "admin",
        "email": "operator",
        "password": {"generate": "password", "length": 24},
    }
    provision_admin_credential(app, admin, db_session)

    env = _env(app)
    assert env["HOP3_ADMIN_USER"] == "admin"
    assert env["HOP3_ADMIN_EMAIL"] == "op@example.com"
    assert len(env["HOP3_ADMIN_PASSWORD"]) >= 20

    cred = read_admin_credential(app, db_session)
    assert cred is not None
    assert cred["username"] == "admin"
    assert cred["email"] == "op@example.com"
    assert cred["password"] == env["HOP3_ADMIN_PASSWORD"]  # stored == injected
    assert cred["source"] == "generated"


def test_provision_is_generate_once(db_session, operator):
    # Redeploy must not rotate the password (ADR 046 generate-once).
    app = _app(db_session)
    admin = {"email": "operator", "password": {"generate": "password"}}
    provision_admin_credential(app, admin, db_session)
    first = _env(app)["HOP3_ADMIN_PASSWORD"]
    provision_admin_credential(app, admin, db_session)
    assert _env(app)["HOP3_ADMIN_PASSWORD"] == first


def test_provision_username_only_injects_no_email(db_session, operator):
    app = _app(db_session)
    provision_admin_credential(
        app, {"username": "admin", "password": {"generate": "password"}}, db_session
    )
    env = _env(app)
    assert env["HOP3_ADMIN_USER"] == "admin"
    assert "HOP3_ADMIN_EMAIL" not in env


def test_provision_noop_without_admin(db_session):
    app = _app(db_session)
    provision_admin_credential(app, {}, db_session)
    assert read_admin_credential(app, db_session) is None
    assert "HOP3_ADMIN_PASSWORD" not in _env(app)


def test_operator_email_required_when_referenced(db_session, monkeypatch):
    monkeypatch.setattr(admin_bootstrap, "config", SimpleNamespace(OPERATOR_EMAIL=""))
    app = _app(db_session)
    with pytest.raises(AdminBootstrapError, match="operator email"):
        provision_admin_credential(
            app, {"email": "operator", "password": {"generate": "password"}}, db_session
        )


def test_resolve_email_forms():
    assert resolve_admin_email(None) is None
    assert resolve_admin_email("a@b.com") == "a@b.com"


def test_surface_prints_once_only(db_session, operator, monkeypatch):
    # Surfaced exactly once, guarded by the credential's `surfaced` flag, so a
    # redeploy never re-prints the password.
    app = _app(db_session)
    set_env_vars(app, {"HOST_NAME": "wiki.example.com"}, db_session)
    provision_admin_credential(
        app, {"email": "operator", "password": {"generate": "password"}}, db_session
    )
    pw = _env(app)["HOP3_ADMIN_PASSWORD"]

    lines: list[str] = []
    monkeypatch.setattr(admin_bootstrap, "log", lambda msg="", **_k: lines.append(msg))

    surface_admin_credential(app, db_session)
    out = "\n".join(lines)
    assert pw in out
    assert "op@example.com" in out

    lines.clear()
    surface_admin_credential(app, db_session)  # a later redeploy
    assert lines == []  # never re-printed


def test_surface_noop_without_credential(db_session, monkeypatch):
    app = _app(db_session)
    lines: list[str] = []
    monkeypatch.setattr(admin_bootstrap, "log", lambda msg="", **_k: lines.append(msg))
    surface_admin_credential(app, db_session)  # must not raise
    assert lines == []


def test_bootstrap_runs_create_once(db_session, operator):
    app = _app(db_session)
    admin = {
        "email": "operator",
        "password": {"generate": "password"},
        "create": "create-admin",
    }
    provision_admin_credential(app, admin, db_session)

    calls: list[str] = []
    bootstrap_admin_account(app, admin, db_session, calls.append)
    bootstrap_admin_account(app, admin, db_session, calls.append)  # a redeploy
    assert calls == ["create-admin"]  # run exactly once


def test_bootstrap_fails_loud(db_session, operator):
    app = _app(db_session)
    admin = {
        "email": "operator",
        "password": {"generate": "password"},
        "create": "boom",
    }
    provision_admin_credential(app, admin, db_session)

    def boom(_cmd: str) -> None:
        msg = "nonzero exit"
        raise RuntimeError(msg)

    with pytest.raises(AdminBootstrapError, match="bootstrap failed"):
        bootstrap_admin_account(app, admin, db_session, boom)


def test_bootstrap_noop_without_create(db_session, operator):
    # No `create` -> the app self-bootstraps from env; the platform runs nothing.
    app = _app(db_session)
    admin = {"email": "operator", "password": {"generate": "password"}}
    provision_admin_credential(app, admin, db_session)
    calls: list[str] = []
    bootstrap_admin_account(app, admin, db_session, calls.append)
    assert calls == []


def test_docker_create_fails_loud(db_session, operator):
    # A Docker app declaring [admin].create must abort loudly (recipe commands
    # don't run on the compose path) rather than silently skip the bootstrap.
    app = _app(db_session)
    app_config = SimpleNamespace(
        has_hop3_toml=True,
        hop3_config=SimpleNamespace(
            admin={
                "email": "operator",
                "password": {"generate": "password"},
                "create": "make-admin",
            },
            # The bootstrap step now also creates Hop3's own probe account; this
            # app declares none, which is the opt-out.
            probe={},
        ),
    )
    with pytest.raises(AdminBootstrapError, match="not supported for the Docker"):
        # Stubs are intentional: the docker guard raises before app_config's full
        # type or build_artifact is used.
        _bootstrap_admin_account(app, app_config, None, "docker-compose", db_session)  # ty: ignore[invalid-argument-type]


def test_credential_block_marks_the_sign_in_field():
    """
    The reveal must name the field the app authenticates on.

    Regression: BookStack lists a username and an email; signing in with the
    username is rejected as a bad password, so an unmarked block sends the
    operator straight into "these credentials do not match our records".
    """
    cred = {"username": "admin", "email": "a@b.com", "password": "pw", "login": "email"}
    block = format_admin_credential("bookstack", "bs.example.com", cred)

    email_line = next(ln for ln in block.splitlines() if "a@b.com" in ln)
    user_line = next(ln for ln in block.splitlines() if "Username:" in ln)
    assert "sign in with this" in email_line
    assert "sign in with this" not in user_line


def test_credential_block_without_a_login_hint_marks_nothing():
    """Credentials stored before the hint existed still render cleanly."""
    cred = {"username": "admin", "email": "a@b.com", "password": "pw"}
    block = format_admin_credential("legacy", "l.example.com", cred)

    assert "sign in with this" not in block
    assert "admin" in block
    assert "a@b.com" in block


def test_create_commands_get_the_artifact_runtime_env(
    db_session, operator, monkeypatch
):
    """
    A create command runs the APP's code and needs the app's runtime.

    `run_create` built its environment from `os.environ` plus the app's own
    vars, and never applied the build artifact's `env_vars` — the ones the
    toolchain establishes. For a Nix app that is where LD_LIBRARY_PATH lives,
    so bugsink's `[probe].create` invoked `bugsink-manage` and Django could not
    load psycopg: the exact library set the recipe declared was applied when
    spawning workers and nowhere else.
    """
    seen: dict[str, str] = {}

    def fake_shell(command, cwd=None, env=None, check=True):
        seen.update(env or {})
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("hop3.deployers.deployer.shell", fake_shell)

    app = _app(db_session)
    set_env_vars(app, {"HOST_NAME": "b.example.com", "OWN": "app-wins"}, db_session)
    admin = {
        "email": "operator",
        "password": {"generate": "password"},
        "create": "make-admin",
    }
    provision_admin_credential(app, admin, db_session)
    app_config = SimpleNamespace(
        has_hop3_toml=True,
        hop3_config=SimpleNamespace(admin=admin, probe={}),
    )
    build_artifact = SimpleNamespace(
        runtime=SimpleNamespace(
            path_prepend=[],
            env_vars={"LD_LIBRARY_PATH": "/nix/store/pg/lib", "OWN": "artifact-loses"},
        )
    )

    _bootstrap_admin_account(app, app_config, build_artifact, "uwsgi", db_session)  # ty: ignore[invalid-argument-type]

    assert seen.get("LD_LIBRARY_PATH") == "/nix/store/pg/lib", (
        "the artifact's runtime env must reach create commands"
    )
    assert seen.get("OWN") == "app-wins", "the app's own value still wins"
