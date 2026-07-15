# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`App.destroy()` is a complete, verifiable, loud teardown.

Regression for the audit finding that destroy()'s "we preserve data" branch was
dead code (the parent app_path was already deleted), so data/ and volumes/ were
silently removed while the docstring claimed otherwise. destroy() now removes
everything (complete teardown — no leftover disk) but warns loudly first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.config import HopConfig
from hop3.orm import App

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def _tmp_hop3(tmp_path: Path, monkeypatch):
    HopConfig.reset_instance()
    HopConfig.set_instance(HopConfig(hop3_root=tmp_path))
    # Isolate destroy() from process reaping and Docker cleanup.
    monkeypatch.setattr("hop3.run.reaper.reap_app_processes", lambda _name: [])
    monkeypatch.setattr(App, "_cleanup_orphan_docker_resources", lambda self: None)
    yield
    HopConfig.reset_instance()


@pytest.mark.usefixtures("_tmp_hop3")
def test_destroy_removes_data_and_volumes_and_warns(monkeypatch):
    app = App(name="destroyme")
    (app.data_path).mkdir(parents=True)
    (app.data_path / "important.txt").write_text("keep me?")
    (app.volumes_path / "store").mkdir(parents=True)
    (app.volumes_path / "store" / "secret.txt").write_text("precious")

    messages: list[str] = []
    monkeypatch.setattr(
        "hop3.orm.app.log", lambda *a, **k: messages.append(a[0] if a else "")
    )

    app.destroy()

    # Complete teardown: nothing left on disk (no leftover, no false preserve).
    assert not app.app_path.exists()
    assert not app.data_path.exists()
    assert not app.volumes_path.exists()

    # ...but it warned loudly about the data and volumes it removed.
    joined = "\n".join(messages)
    assert "permanently" in joined
    assert "data" in joined
    assert "volumes" in joined
    # The old dead-code lie must be gone.
    assert "Preserving folder" not in joined
