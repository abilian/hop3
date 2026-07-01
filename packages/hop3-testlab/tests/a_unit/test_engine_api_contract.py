# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""The hop3-testing (engine) API surface the Test Lab imports (ADR 052 Phase 0).

The Lab reaches into engine internals that CLI deprecation aliases don't cover.
ADR 052 refactors the engine (e.g. collapses the cloud deploy wrapper); these
must survive with the same import paths and signatures the Lab uses, or the Lab
must be updated in the same change (ADR 052 rule R3). This is a compile-time
tripwire for signature/import drift — construction only, no network.
"""

from __future__ import annotations

import inspect


def test_catalog_surface_imports():
    from hop3_testing.catalog import Catalog, default_scan_paths
    from hop3_testing.targets.helpers import find_project_root

    assert callable(default_scan_paths)
    assert callable(find_project_root)
    assert inspect.isclass(Catalog)


def test_result_store_surface_imports():
    from hop3_testing.results import ResultStore
    from hop3_testing.results.store import make_store_engine

    assert inspect.isclass(ResultStore)
    assert callable(make_store_engine)


def test_mode_config_surface_imports():
    from hop3_testing.selector.modes import get_mode_config

    assert callable(get_mode_config)


def test_hetzner_surface_matches_worker_usage():
    # Mirrors hop3_testlab.worker._hetzner_manager: HetznerManager(HetznerConfig(...))
    from hop3_testing.system_tests.config import HetznerConfig
    from hop3_testing.system_tests.hetzner import HetznerManager

    config = HetznerConfig(
        api_token="tok",
        server_id=123,
        image="ubuntu-24.04",
        ssh_key_name="lab-key",
        ssh_key_path="/home/hop3/.ssh/id_ed25519",
    )
    manager = HetznerManager(config)

    # The three methods the Lab drives (blank-slate rebuild + pre-flight checks).
    for method in ("get_server_info", "resolve_ssh_key", "rebuild_server"):
        assert callable(getattr(manager, method)), f"HetznerManager.{method} missing"
    # rebuild_server(image=..., timeout=...) — the kwargs worker.py passes.
    params = inspect.signature(manager.rebuild_server).parameters
    assert "image" in params
    assert "timeout" in params
