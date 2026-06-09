# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""The `coverage` mode: a representative subset that still hits every case.

It must exercise every variant / toolchain / addon / category at least once
(set-cover) while dropping redundant apps that share a cell — the basis for a
profile that's a fraction of nightly's cost.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from hop3_testing.catalog.models import (
    DemoConfig,
    Priority,
    TargetType,
    TestDefinition,
    TestMetadata,
    TestRequirements,
    Tier,
    TutorialConfig,
)
from hop3_testing.selector import Selector, get_mode_config
from hop3_testing.selector.selector import (
    _DEMO_FLOOR,
    _coverage_cells,
    reduce_to_representatives,
    select_coverage,
)


def _mk(
    name: str,
    *,
    covers: tuple[str, ...] = (),
    services: tuple[str, ...] = (),
    priority: str = "P1",
    tier: str = "fast",
    kind: str = "deployment",
) -> TestDefinition:
    kwargs: dict = {
        "name": name,
        "tier": Tier(tier),
        "priority": Priority(priority),
        "requirements": TestRequirements(
            targets=[TargetType.DOCKER], services=list(services)
        ),
        "metadata": TestMetadata(covers=list(covers)),
    }
    if kind == "demo":
        kwargs["demo"] = DemoConfig()
    elif kind == "tutorial":
        kwargs["tutorial"] = TutorialConfig(path="x")
    return TestDefinition(**kwargs)


def _matrix() -> list[TestDefinition]:
    """A small but redundant matrix (17 tests across the real dimensions)."""
    return [
        # One PHP app shipped in all four packaging variants (uses mysql).
        _mk("apps/real-apps-native/shop", covers=("php",), services=("mysql",)),
        _mk("apps/real-apps-docker/shop", covers=("php",), services=("mysql",)),
        _mk("apps/real-apps-nix/shop", covers=("php",), services=("mysql",)),
        _mk("apps/real-apps-nix-gen/shop", covers=("php",), services=("mysql",)),
        # Redundant python-native apps (no addon) — only one is needed.
        _mk("apps/real-apps-native/py1", covers=("python",)),
        _mk("apps/real-apps-native/py2", covers=("python",)),
        _mk("apps/real-apps-native/py3", covers=("python",)),
        # Python-docker: two carry distinct addons, three are pure redundancy.
        _mk("apps/real-apps-docker/pg", covers=("python",), services=("postgres",)),
        _mk("apps/real-apps-docker/rd", covers=("python",), services=("redis",)),
        _mk("apps/real-apps-docker/pd1", covers=("python",)),
        _mk("apps/real-apps-docker/pd2", covers=("python",)),
        _mk("apps/real-apps-docker/pd3", covers=("python",)),
        # A Go app.
        _mk("apps/real-apps-docker/gosvc", covers=("go",)),
        # Redundant demos + tutorials.
        _mk("demos/demo1", kind="demo"),
        _mk("demos/demo2", kind="demo"),
        _mk("docs/src/tutorials/python/flask", kind="tutorial"),
        _mk("docs/src/tutorials/go/gin", kind="tutorial"),
    ]


def _cells(tests: list[TestDefinition]) -> set[str]:
    out: set[str] = set()
    for t in tests:
        out |= _coverage_cells(t)
    return out


def test_coverage_mode_is_representative():
    cfg = get_mode_config("coverage")
    assert cfg.representative is True
    assert cfg.targets == ["docker"]  # docker-only keeps it cheap


def test_reduction_preserves_every_cell_but_shrinks_the_set():
    tests = _matrix()
    reduced = reduce_to_representatives(tests)

    # No significant case is lost.
    assert _cells(reduced) == _cells(tests)
    # And it's genuinely smaller.
    assert len(reduced) < len(tests)


def test_reduction_drops_apps_that_share_a_cell():
    reduced = {t.name for t in reduce_to_representatives(_matrix())}

    # All four PHP variants survive — each is the only app covering its
    # variant/php cell (that's a "significant case", not redundancy).
    for v in ("native", "docker", "nix", "nix-gen"):
        assert f"apps/real-apps-{v}/shop" in reduced

    # The three addon-less python-docker apps add nothing once pg+redis are in.
    assert not (
        {
            "apps/real-apps-docker/pd1",
            "apps/real-apps-docker/pd2",
            "apps/real-apps-docker/pd3",
        }
        & reduced
    )
    # At most one of the redundant python-native apps is kept.
    assert (
        len(
            {
                "apps/real-apps-native/py1",
                "apps/real-apps-native/py2",
                "apps/real-apps-native/py3",
            }
            & reduced
        )
        == 1
    )
    # One demo and one tutorial language each is enough for their cells.
    assert len({"demos/demo1", "demos/demo2"} & reduced) == 1


def test_reduction_is_deterministic():
    a = [t.name for t in reduce_to_representatives(_matrix())]
    b = [t.name for t in reduce_to_representatives(_matrix())]
    assert a == b


def test_coverage_keeps_all_tutorials_floors_demos_setcovers_deploy():
    tests = []
    # 20 plain demos (no covers) collapse to one cell under pure set-cover.
    tests += [_mk(f"demos/demo{i}", kind="demo") for i in range(20)]
    # Tutorials: two share a language — every one is still a distinct path.
    for path, lang in [
        ("python/flask", "python"),
        ("python/django", "python"),
        ("go/gin", "go"),
        ("elixir/phoenix", "elixir"),
        ("rust/axum", "rust"),
    ]:
        tests.append(_mk(f"docs/src/tutorials/{path}", covers=(lang,), kind="tutorial"))
    # Two redundant python-docker deployment apps -> set-cover keeps one.
    tests.append(_mk("apps/real-apps-docker/a", covers=("python",)))
    tests.append(_mk("apps/real-apps-docker/b", covers=("python",)))

    by = Counter(t.runner_type for t in select_coverage(tests))
    assert by["tutorial"] == 5  # all tutorials kept
    assert by["demo"] == _DEMO_FLOOR  # floored, not collapsed to 1
    assert by["deployment"] == 1  # redundant deploy apps collapse


def test_demo_floor_caps_at_what_exists():
    tests = [_mk(f"demos/demo{i}", kind="demo") for i in range(3)]
    demos = [t for t in select_coverage(tests) if t.runner_type == "demo"]
    assert len(demos) == 3  # only 3 exist; floor can't invent more


class _StubCatalog:
    """Minimal catalog: returns a fixed list regardless of filter args."""

    def __init__(self, tests: list[TestDefinition]) -> None:
        self._tests = tests

    def filter(self, **_kwargs) -> list[TestDefinition]:
        return list(self._tests)


def test_selector_applies_reduction_only_for_coverage_mode():
    catalog = _StubCatalog(_matrix())
    selector = Selector(catalog=cast("Any", catalog))

    full = selector.select(get_mode_config("nightly"))
    covered = selector.select(get_mode_config("coverage"))

    assert len(covered) < len(full)
    assert _cells(covered) == _cells(full)  # same coverage, fewer tests
