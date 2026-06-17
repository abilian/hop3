# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""The `tag-coverage` and `combo-coverage` modes.

``tag-coverage``: minimal subset covering every individual tag value at least once.
``combo-coverage``: minimal subset covering every observed 5-tuple at least once.

Each uses greedy set-cover to drop redundant tests while preserving full coverage
of the relevant dimension — the basis for profiles that are a fraction of
nightly's cost.
"""

from __future__ import annotations

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
    _combo_cells,
    _tag_cells,
    reduce_to_representatives,
    select_combo_coverage,
    select_tag_coverage,
)


def _mk(
    name: str,
    *,
    builder: str | None = None,
    toolchain: str | None = None,
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
        "metadata": TestMetadata(
            builder=builder,
            toolchain=toolchain,
            spec="hop3toml",
        ),
    }
    if kind == "demo":
        kwargs["demo"] = DemoConfig()
        kwargs["metadata"] = TestMetadata(
            builder=builder, toolchain=toolchain, spec="demo"
        )
    elif kind == "tutorial":
        kwargs["tutorial"] = TutorialConfig(path="x")
        kwargs["metadata"] = TestMetadata(
            builder=builder, toolchain=toolchain, spec="tutorial"
        )
    return TestDefinition(**kwargs)


# --- Tag cells -------------------------------------------------------------


def test_tag_cells_captures_all_axes():
    t = _mk("apps/real-apps-native/app1", builder="native", toolchain="python",
            services=("mysql", "redis"))
    cells = _tag_cells(t)
    assert "builder:native" in cells
    assert "toolchain:python" in cells
    assert "addon:mysql" in cells
    assert "addon:redis" in cells
    assert "category:deployment" in cells
    assert "spec:hop3toml" in cells


def test_tag_cells_omits_none_fields():
    t = _mk("apps/x", builder=None, toolchain=None)
    cells = _tag_cells(t)
    assert not any(c.startswith("builder:") for c in cells)
    assert not any(c.startswith("toolchain:") for c in cells)


# --- Combo cells -----------------------------------------------------------


def test_combo_cell_is_single_string():
    t = _mk("apps/x", builder="native", toolchain="python", services=("mysql", "redis"))
    cells = _combo_cells(t)
    assert len(cells) == 1
    assert "combo:native/python/mysql+redis/deployment/hop3toml" in cells


def test_combo_cells_identical_when_same_tuple():
    t1 = _mk("apps/x", builder="native", toolchain="python")
    t2 = _mk("apps/y", builder="native", toolchain="python")
    assert _combo_cells(t1) == _combo_cells(t2)


# --- Tag coverage ----------------------------------------------------------


def _tag_matrix() -> list[TestDefinition]:
    """A matrix where two tests cover all tags, the third adds nothing new."""
    return [
        _mk("apps/native/py-pg", builder="native", toolchain="python",
            services=("postgres",)),
        _mk("apps/native/go-pg", builder="native", toolchain="go",
            services=("postgres",)),
        _mk("apps/native/py-x", builder="native", toolchain="python"),
    ]


def test_tag_coverage_drops_redundant():
    selected = select_tag_coverage(_tag_matrix())
    names = {t.name for t in selected}
    assert "apps/native/py-pg" in names  # covers python, native, postgres
    assert "apps/native/go-pg" in names  # covers go
    assert "apps/native/py-x" not in names  # python+native already covered


def test_tag_coverage_preserves_all_tag_values():
    tests = _tag_matrix()
    reduced = select_tag_coverage(tests)
    all_tags: set[str] = set()
    for t in tests:
        all_tags |= _tag_cells(t)
    reduced_tags: set[str] = set()
    for t in reduced:
        reduced_tags |= _tag_cells(t)
    assert reduced_tags == all_tags


# --- Combo coverage --------------------------------------------------------


def _combo_matrix() -> list[TestDefinition]:
    """Four tests forming three distinct combos."""
    return [
        # combo A: native/python/hop3toml
        _mk("apps/native/py1", builder="native", toolchain="python"),
        # combo A again — redundant
        _mk("apps/native/py2", builder="native", toolchain="python"),
        # combo B: native/go/hop3toml
        _mk("apps/native/go1", builder="native", toolchain="go"),
        # combo C: nix/python/hop3toml
        _mk("apps/nix/py1", builder="nix", toolchain="python"),
    ]


def test_combo_coverage_drops_same_combo():
    selected = select_combo_coverage(_combo_matrix())
    names = {t.name for t in selected}
    assert len(names) == 3  # 3 unique combos
    assert names >= {"apps/native/go1", "apps/nix/py1"}
    # Exactly one of the two identical-combo tests survives.
    assert len({"apps/native/py1", "apps/native/py2"} & names) == 1


def test_combo_coverage_preserves_every_combo():
    tests = _combo_matrix()
    reduced = select_combo_coverage(tests)
    all_combos: set[str] = set()
    for t in tests:
        all_combos |= _combo_cells(t)
    reduced_combos: set[str] = set()
    for t in reduced:
        reduced_combos |= _combo_cells(t)
    assert reduced_combos == all_combos


# --- Determinism -----------------------------------------------------------


def test_reduction_is_deterministic():
    a = [t.name for t in reduce_to_representatives(_tag_matrix())]
    b = [t.name for t in reduce_to_representatives(_tag_matrix())]
    assert a == b


def test_combo_reduction_is_deterministic():
    a = [t.name for t in reduce_to_representatives(_combo_matrix(), cell_fn=_combo_cells)]
    b = [t.name for t in reduce_to_representatives(_combo_matrix(), cell_fn=_combo_cells)]
    assert a == b


# --- Modes ----------------------------------------------------------------


def test_tag_coverage_mode_exists():
    cfg = get_mode_config("tag-coverage")
    assert cfg.representative is True
    assert cfg.targets == ["docker"]


def test_combo_coverage_mode_exists():
    cfg = get_mode_config("combo-coverage")
    assert cfg.representative is True
    assert cfg.targets == ["docker"]


def test_old_coverage_is_alias_for_combo():
    assert get_mode_config("coverage").name == "combo-coverage"


# --- Selector routing -----------------------------------------------------


class _StubCatalog:
    def __init__(self, tests: list[TestDefinition]) -> None:
        self._tests = tests

    def filter(self, **_kwargs) -> list[TestDefinition]:
        return list(self._tests)


def test_selector_routes_tag_coverage():
    catalog = _StubCatalog(_tag_matrix())
    selector = Selector(catalog=cast("Any", catalog))

    full = selector.select(get_mode_config("nightly"))
    covered = selector.select(get_mode_config("tag-coverage"))

    assert len(covered) < len(full)
    all_tags: set[str] = set()
    for t in full:
        all_tags |= _tag_cells(t)
    covered_tags: set[str] = set()
    for t in covered:
        covered_tags |= _tag_cells(t)
    assert covered_tags == all_tags


def test_selector_routes_combo_coverage():
    catalog = _StubCatalog(_combo_matrix())
    selector = Selector(catalog=cast("Any", catalog))

    full = selector.select(get_mode_config("nightly"))
    covered = selector.select(get_mode_config("combo-coverage"))

    assert len(covered) < len(full)
