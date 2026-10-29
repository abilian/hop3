# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The addon commands, run against a fake addon type registered through the hook.

The fake addon ``fakedb`` is a real plugin as far as Hop3 can tell: it comes
back from ``get_addons()`` and records its instances in the addon secrets
store, the registry every command reads. Its "server" can be taken down to
see what each command does when the backing service does not answer.

Each test asserts the state a command leaves behind: credential rows, the
app's environment, the instances on record.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from hop3.commands.services import (
    AddonAttachCmd,
    AddonCreateCmd,
    AddonDestroyCmd,
    AddonDetachCmd,
    AddonShowCmd,
)
from hop3.config import HopConfig
from hop3.core.credentials import get_credential_encryptor
from hop3.core.hooks import hookimpl
from hop3.core.plugins import get_plugin_manager
from hop3.orm import AddonCredential, App, EnvVar
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    EnvVarRepository,
)
from hop3.plugins.addons.secrets import (
    delete_addon_secrets,
    list_addon_instances,
    load_addon_secrets,
    save_addon_secrets,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

FAKE = "fakedb"


class FakeAddon:
    """An addon whose instances live in the secrets store; ``down`` breaks it."""

    name: ClassVar[str] = FAKE
    down: ClassVar[bool] = False

    def __init__(self, addon_name: str) -> None:
        self.addon_name = addon_name

    def _answer(self) -> None:
        if FakeAddon.down:
            msg = "fakedb is not answering on 127.0.0.1:9999"
            raise ConnectionError(msg)

    def create(self) -> None:
        self._answer()
        save_addon_secrets(FAKE, self.addon_name, {"password": "pw"})

    def exists(self) -> bool:
        self._answer()
        return load_addon_secrets(FAKE, self.addon_name) is not None

    def destroy(self) -> None:
        self._answer()
        delete_addon_secrets(FAKE, self.addon_name)

    def get_connection_details(self) -> dict[str, str]:
        self._answer()
        if load_addon_secrets(FAKE, self.addon_name) is None:
            msg = f"No fakedb addon '{self.addon_name}'"
            raise RuntimeError(msg)
        return {
            "DATABASE_URL": f"fake://u:pw@127.0.0.1:9999/{self.addon_name}",
            "FAKE_HOST": "127.0.0.1",
        }

    def info(self) -> dict[str, Any]:
        self._answer()
        return {"addon_name": self.addon_name, "type": FAKE, "size_mb": 42.5}


class _FakePlugin:
    @hookimpl
    def get_addons(self) -> list:
        return [FakeAddon]


@pytest.fixture(autouse=True)
def fakedb(tmp_path, monkeypatch) -> Iterator[type[FakeAddon]]:
    """Register ``fakedb`` with the plugin manager, over an empty registry."""
    monkeypatch.setattr(HopConfig, "_instance", HopConfig(hop3_root=tmp_path))
    monkeypatch.setattr(FakeAddon, "down", False)
    pm = get_plugin_manager()
    plugin = _FakePlugin()
    pm.register(plugin)
    yield FakeAddon
    pm.unregister(plugin)


@pytest.fixture
def credential_repo(db_session: Session) -> AddonCredentialRepository:
    return AddonCredentialRepository(session=db_session)


@pytest.fixture
def attach(db_session: Session, credential_repo) -> AddonAttachCmd:
    return AddonAttachCmd(
        app_repo=AppRepository(session=db_session),
        addon_credential_repo=credential_repo,
        env_var_repo=EnvVarRepository(session=db_session),
    )


@pytest.fixture
def detach(db_session: Session, credential_repo) -> AddonDetachCmd:
    return AddonDetachCmd(
        app_repo=AppRepository(session=db_session),
        addon_credential_repo=credential_repo,
        env_var_repo=EnvVarRepository(session=db_session),
    )


@pytest.fixture
def destroy(credential_repo) -> AddonDestroyCmd:
    return AddonDestroyCmd(addon_credential_repo=credential_repo)


def _app(session: Session, name: str = "web") -> App:
    app = App(name=name, hostname=f"{name}.example.com", port=8000)
    session.add(app)
    session.commit()
    return app


def _env(session: Session, app: App) -> dict[str, str]:
    session.expire_all()
    rows = session.query(EnvVar).filter_by(app_id=app.id).all()
    return {row.name: row.value for row in rows}


def _credentials(session: Session, **filters: object) -> list[AddonCredential]:
    session.expire_all()
    return session.query(AddonCredential).filter_by(**filters).all()


def _created(*names: str) -> None:
    for addon_name in names:
        AddonCreateCmd().call(FAKE, addon_name)


# --- create -------------------------------------------------------------------


def test_create_requires_type_and_name():
    with pytest.raises(ValueError, match="Usage: hop3 addon create"):
        AddonCreateCmd().call()


def test_create_records_the_instance():
    result = AddonCreateCmd().call(FAKE, "my-db")

    assert (FAKE, "my-db") in list_addon_instances()
    assert "created successfully" in result[0]["text"]
    assert result[-1]["t"] == "summary"


def test_create_refuses_an_unsafe_name():
    result = AddonCreateCmd().call(FAKE, "a;drop")

    assert result[0]["t"] == "error"
    assert list_addon_instances() == []


def test_create_of_an_unknown_type_names_the_available_ones():
    with pytest.raises(ValueError, match=f"not found.*{FAKE}"):
        AddonCreateCmd().call("nosuchdb", "my-db")


def test_create_against_a_server_that_is_down_fails(fakedb):
    fakedb.down = True

    with pytest.raises(ValueError, match="not answering"):
        AddonCreateCmd().call(FAKE, "my-db")
    assert list_addon_instances() == []


# --- attach -------------------------------------------------------------------


def test_attach_requires_app(db_session, attach):
    with pytest.raises(ValueError, match="--app is required"):
        attach.call("my-db")
    assert _credentials(db_session) == []


def test_attach_to_a_missing_app_stores_nothing(db_session, attach):
    _created("my-db")

    with pytest.raises(ValueError, match="not found"):
        attach.call("my-db", "--app", "ghost", "--type", FAKE)
    assert _credentials(db_session) == []


def test_attach_stores_the_credential_and_injects_the_env(db_session, attach):
    app = _app(db_session)
    _created("my-db")

    attach.call("my-db", "--app", "web")

    (credential,) = _credentials(db_session, app_id=app.id)
    assert (credential.addon_type, credential.addon_name) == (FAKE, "my-db")
    stored = get_credential_encryptor().decrypt(credential.encrypted_data)
    assert stored["DATABASE_URL"] == "fake://u:pw@127.0.0.1:9999/my-db"
    assert _env(db_session, app) == stored


def test_attach_overwrites_a_user_set_var_of_the_same_name(db_session, attach):
    app = _app(db_session)
    db_session.add(EnvVar(app_id=app.id, name="DATABASE_URL", value="old"))
    db_session.commit()
    _created("my-db")

    attach.call("my-db", "--app", "web")

    env = _env(db_session, app)
    assert env["DATABASE_URL"] == "fake://u:pw@127.0.0.1:9999/my-db"
    assert len(env) == 2


def test_a_second_addon_of_a_type_gets_prefixed_vars(db_session, attach):
    app = _app(db_session)
    _created("db1", "db2")

    attach.call("db1", "--app", "web")
    attach.call("db2", "--app", "web")

    env = _env(db_session, app)
    assert env["DATABASE_URL"].endswith("/db1")
    assert env["DB2_DATABASE_URL"].endswith("/db2")
    assert len(_credentials(db_session, app_id=app.id)) == 2


def test_attach_to_a_server_that_is_down_stores_nothing(db_session, attach, fakedb):
    app = _app(db_session)
    _created("my-db")
    fakedb.down = True

    with pytest.raises(ValueError, match="not answering"):
        attach.call("my-db", "--app", "web")
    assert _credentials(db_session) == []
    assert _env(db_session, app) == {}


# --- detach -------------------------------------------------------------------


def test_detach_requires_app(detach):
    with pytest.raises(ValueError, match="--app is required"):
        detach.call("my-db", "--type", FAKE)


def test_detach_from_a_missing_app_fails(detach):
    with pytest.raises(ValueError, match="not found"):
        detach.call("my-db", "--app", "ghost", "--type", FAKE)


def test_detach_removes_the_credential_and_its_vars(db_session, attach, detach):
    app = _app(db_session)
    db_session.add(EnvVar(app_id=app.id, name="SECRET_KEY", value="mine"))
    db_session.commit()
    _created("my-db")
    attach.call("my-db", "--app", "web")

    detach.call("my-db", "--app", "web")

    assert _credentials(db_session, app_id=app.id) == []
    assert _env(db_session, app) == {"SECRET_KEY": "mine"}


def test_detach_of_an_unattached_addon_says_so(db_session, detach):
    _app(db_session)

    result = detach.call("my-db", "--app", "web", "--type", FAKE)

    assert "was not attached" in result[0]["text"]


def test_detach_leaves_the_other_addons_alone(db_session, attach, detach):
    app = _app(db_session)
    _created("db1", "db2")
    attach.call("db1", "--app", "web")
    attach.call("db2", "--app", "web")

    detach.call("db1", "--app", "web")

    (remaining,) = _credentials(db_session, app_id=app.id)
    assert remaining.addon_name == "db2"
    # db2 was promoted: it now owns the unprefixed vars.
    assert _env(db_session, app)["DATABASE_URL"].endswith("/db2")
    assert "DB2_DATABASE_URL" not in _env(db_session, app)


def _corrupt_credential(session: Session, app: App, addon_name: str) -> None:
    (credential,) = _credentials(session, app_id=app.id, addon_name=addon_name)
    credential.encrypted_data = "not-a-fernet-token"
    session.commit()


def test_detach_with_an_unreadable_credential_uses_the_live_names(
    db_session, attach, detach
):
    app = _app(db_session)
    _created("my-db")
    attach.call("my-db", "--app", "web")
    _corrupt_credential(db_session, app, "my-db")

    detach.call("my-db", "--app", "web")

    assert _credentials(db_session, app_id=app.id) == []
    assert _env(db_session, app) == {}


def test_detach_is_refused_when_no_source_names_the_vars(
    db_session, attach, detach, fakedb
):
    """Deleting the credential then would orphan DATABASE_URL for good."""
    app = _app(db_session)
    _created("my-db")
    attach.call("my-db", "--app", "web")
    _corrupt_credential(db_session, app, "my-db")
    fakedb.down = True

    with pytest.raises(ValueError, match="cannot tell which environment"):
        detach.call("my-db", "--app", "web")

    db_session.rollback()
    assert len(_credentials(db_session, app_id=app.id)) == 1
    assert "DATABASE_URL" in _env(db_session, app)


# --- destroy ------------------------------------------------------------------


def test_destroy_requires_a_name(destroy):
    with pytest.raises(ValueError, match="Usage: hop3 addon destroy"):
        destroy.call()


def test_destroy_removes_the_instance_and_every_attachment(db_session, attach, destroy):
    web, worker = _app(db_session, "web"), _app(db_session, "worker")
    _created("shared-db")
    attach.call("shared-db", "--app", "web")
    attach.call("shared-db", "--app", "worker")

    result = destroy.call("shared-db")

    assert list_addon_instances() == []
    assert _credentials(db_session, addon_name="shared-db") == []
    assert {web.id, worker.id}.isdisjoint(c.app_id for c in _credentials(db_session))
    assert "destroyed successfully" in result[0]["text"]


def test_destroy_of_an_absent_addon_says_so(destroy):
    result = destroy.call("ghost-db", "--type", FAKE)

    assert "does not exist" in result[0]["text"]


def test_destroy_against_a_server_that_is_down_destroys_nothing(
    db_session, attach, destroy, fakedb
):
    """'Does not exist' is an answer; a server that cannot answer is an error."""
    app = _app(db_session)
    _created("my-db")
    attach.call("my-db", "--app", "web")
    fakedb.down = True

    with pytest.raises(ValueError, match="nothing was destroyed"):
        destroy.call("my-db")

    db_session.rollback()
    assert (FAKE, "my-db") in list_addon_instances()
    assert len(_credentials(db_session, app_id=app.id)) == 1


# --- show ---------------------------------------------------------------------


def test_show_requires_a_name():
    with pytest.raises(ValueError, match="Usage: hop3 addon show"):
        AddonShowCmd().call()


def test_show_resolves_the_type_from_the_name_and_prints_the_info():
    _created("my-db")

    (item,) = AddonShowCmd().call("my-db")

    assert f"Type: {FAKE}" in item["text"]
    assert "size_mb: 42.5" in item["text"]


def test_show_of_an_unknown_name_fails():
    with pytest.raises(ValueError, match="No addon named 'ghost'"):
        AddonShowCmd().call("ghost")
