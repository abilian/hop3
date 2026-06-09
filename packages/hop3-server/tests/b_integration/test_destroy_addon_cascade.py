# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Regression tests: `hop3 app destroy` must tear down attached addons.

Without this, addon resources leak forever — most visibly the Redis
logical-db slots (only 1-15 exist), which exhaust after 15 redis apps and
make every later redis deploy fail. See DestroyCmd._destroy_addons.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from hop3.commands.app import DestroyCmd
from hop3.orm import AddonCredential, App


@pytest.fixture
def test_db():
    """In-memory database with all tables."""
    engine = create_engine("sqlite:///:memory:")
    BigIntAuditBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _make_app(session: Session, name: str, *addons: tuple[str, str]) -> App:
    """Create an app and attach the given (addon_type, addon_name) credentials."""
    app = App(name=name, hostname=f"{name}.local", port=8000)
    session.add(app)
    session.commit()
    for addon_type, addon_name in addons:
        session.add(
            AddonCredential(
                app_id=app.id,
                addon_type=addon_type,
                addon_name=addon_name,
                encrypted_data="x",
            )
        )
    session.commit()
    return app


def _recording_get_addon(destroyed: list):
    """Return a get_addon stub that records (type, name) on .destroy()."""

    def _get_addon(addon_type: str, addon_name: str):
        m = MagicMock()
        m.destroy.side_effect = lambda: destroyed.append((addon_type, addon_name))
        return m

    return _get_addon


def test_destroy_tears_down_attached_addons(test_db: Session):
    app = _make_app(
        test_db, "blog", ("postgres", "blog-postgres"), ("redis", "blog-redis")
    )
    destroyed: list = []

    cmd = DestroyCmd(db_session=test_db)
    with patch(
        "hop3.commands.app.get_addon", side_effect=_recording_get_addon(destroyed)
    ):
        cmd._destroy_addons(app)

    assert ("postgres", "blog-postgres") in destroyed
    assert ("redis", "blog-redis") in destroyed


def test_destroy_keeps_addon_shared_with_another_app(test_db: Session):
    # Two apps share the same addon instance — destroying one must not drop it.
    _make_app(test_db, "app1", ("postgres", "shared-db"))
    app2 = _make_app(
        test_db, "app2", ("postgres", "shared-db"), ("redis", "app2-redis")
    )
    destroyed: list = []

    cmd = DestroyCmd(db_session=test_db)
    with patch(
        "hop3.commands.app.get_addon", side_effect=_recording_get_addon(destroyed)
    ):
        cmd._destroy_addons(app2)

    assert ("postgres", "shared-db") not in destroyed  # kept: app1 still uses it
    assert ("redis", "app2-redis") in destroyed  # app2's own addon is freed


def test_destroy_addon_failure_is_best_effort(test_db: Session):
    # A failing addon teardown must not abort the rest of the destroy.
    app = _make_app(test_db, "svc", ("redis", "svc-redis"))

    def _exploding_get_addon(addon_type: str, addon_name: str):
        m = MagicMock()
        m.destroy.side_effect = RuntimeError("redis-cli unreachable")
        return m

    cmd = DestroyCmd(db_session=test_db)
    with patch("hop3.commands.app.get_addon", side_effect=_exploding_get_addon):
        cmd._destroy_addons(app)  # must not raise


def test_full_destroy_invokes_addon_teardown(test_db: Session):
    # End-to-end wiring: call() must run addon teardown before deleting the app.
    _make_app(test_db, "shop", ("redis", "shop-redis"))
    destroyed: list = []

    cmd = DestroyCmd(db_session=test_db)
    with (
        patch(
            "hop3.commands.app.get_addon", side_effect=_recording_get_addon(destroyed)
        ),
        patch.object(App, "stop"),
        patch.object(App, "destroy"),
    ):
        cmd.call("shop")

    assert ("redis", "shop-redis") in destroyed
    # App (and its credentials, via cascade) are gone.
    assert test_db.query(App).filter_by(name="shop").count() == 0
    assert test_db.query(AddonCredential).count() == 0
