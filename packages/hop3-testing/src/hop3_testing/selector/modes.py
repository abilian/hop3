# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Test execution mode configurations.

The built-in modes in ``MODES`` are the seed defaults. Users can override them
(or add their own) from the Test Lab UI; those edits persist to a TOML overrides
file (``$HOP3_TEST_MODES`` → ``~/.hop3/test-modes.toml``) that ``load_modes()``
overlays on top of the built-ins. Every mode-resolution path goes through
``load_modes()`` (``get_mode_config`` / ``list_modes``), so an edit applies
consistently to the web trigger, the scheduler, and the ``hop3-test --mode X``
subprocess the worker spawns.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError

logger = logging.getLogger(__name__)

# Allowed values, exposed so the UI / API can validate edits before saving.
VALID_TIERS = ("fast", "medium", "slow", "very-slow")
VALID_PRIORITIES = ("P0", "P1", "P2")
VALID_TARGETS = ("docker", "remote", "local")


@dataclass
class ModeConfig:
    """
    Configuration for a test execution mode.

    Each mode defines what tests should be run based on tier,
    priority, category, and target type filters.
    """

    name: str
    """Mode name (smoke, ci, curated, tag-coverage, combo-coverage, broad, full)."""

    tiers: list[str]
    """Allowed tiers (fast, medium, slow, very-slow). Ignored when ``tests`` is
    set (an explicit-list profile bypasses filtering)."""

    priorities: list[str]
    """Allowed priorities (P0, P1, P2). Ignored when ``tests`` is set."""

    targets: list[str]
    """Allowed target types (docker, remote, local)."""

    description: str = ""
    """Human-readable description of this mode."""

    max_duration_minutes: int | None = None
    """Expected maximum duration in minutes."""

    representative: bool = False
    """If True, reduce the filtered set to a minimal representative subset that
    still exercises every significant case (set-cover).  Used by ``tag-coverage``
    and ``combo-coverage`` to hit all significant cases at a fraction of the
    broad suite's cost."""

    tests: list[str] = field(default_factory=list)
    """Explicit list of test names (catalog ids). When non-empty this is a
    *curated* profile: the selector returns exactly these tests, in order, and
    the tier/priority filters above are ignored. Edited via the Test Lab
    profile picker; persisted to the overrides file."""


# Seed for the curated profile: a hand-picked, fast, diverse slice that hits
# many languages and packaging variants plus the simplest demos and a few
# tutorials, targeting < 30 min. It's a normal built-in (resettable), and the
# list is fully editable from the Test Lab profile picker.
_CURATED_SEED: list[str] = [
    # deployment — one fast test per language / packaging variant
    "apps/test-apps-procfile/000-static",
    "apps/test-apps-procfile/010-flask-pip-wsgi",
    "apps/test-apps-procfile/020-nodejs-express",
    "apps/test-apps-procfile/030-golang-gin",
    "apps/test-apps-procfile/030-rack",
    "apps/test-apps-procfile/050-clojure",
    "apps/test-apps-nix/golang-minimal",
    "apps/test-apps-nix/static-hello",
    # One real application, from the catalog. Named by its ID, not its path:
    # a catalog test's name is its app id (`isso`), because its directory sits
    # outside this repo and so has no path relative to the root — while a local
    # fixture is still named `apps/test-apps-procfile/000-static`. A path here
    # matches nothing, silently, and the fast set just gets smaller.
    "isso",
    # demos — the three simplest (run in order; fail-fast stops the rest)
    "demos/demo01",
    "demos/demo02",
    "demos/demo03",
    # tutorials — a diverse language sample
    "docs/tutorials/python/flask.md",
    "docs/tutorials/javascript/express.md",
    "docs/tutorials/go/gin.md",
    "docs/tutorials/ruby/sinatra.md",
    "docs/tutorials/static/static-site.md",
    "docs/tutorials/php/symfony.md",
]


# Pre-defined mode configurations: a size ladder from smallest to largest.
MODES: dict[str, ModeConfig] = {
    "smoke": ModeConfig(
        name="smoke",
        tiers=["fast"],
        priorities=["P0"],
        targets=["docker"],
        description="Smallest sanity smoke (fast + P0 deployment apps).",
        max_duration_minutes=5,
    ),
    "ci": ModeConfig(
        name="ci",
        tiers=["fast", "medium"],
        priorities=["P0"],
        targets=["docker"],
        description="Pre-merge gate (fast+medium + P0).",
        max_duration_minutes=15,
    ),
    "curated": ModeConfig(
        name="curated",
        tiers=[],
        priorities=[],
        targets=["docker"],
        description=(
            "Hand-picked, fast, diverse: a representative test per language and "
            "packaging variant, the simplest demos, and a few tutorials. Edit "
            "the list in the Test Lab profile picker. Target < 30 min."
        ),
        max_duration_minutes=30,
        tests=list(_CURATED_SEED),
    ),
    "tag-coverage": ModeConfig(
        name="tag-coverage",
        tiers=["fast", "medium", "slow"],
        priorities=["P0", "P1"],
        targets=["docker"],
        description=(
            "Tag coverage (docker-only): minimal subset covering every individual "
            "tag value (builder, toolchain, addon, category, spec) at least once. "
            "Fastest way to exercise every significant dimension."
        ),
        max_duration_minutes=30,
        representative=True,
    ),
    "combo-coverage": ModeConfig(
        name="combo-coverage",
        tiers=["fast", "medium", "slow"],
        priorities=["P0", "P1"],
        targets=["docker"],
        description=(
            "Combo coverage (docker-only): minimal subset covering every observed "
            "5-tuple (builder × toolchain × addons × category × spec) at least "
            "once. Every unique combination, well under the broad suite."
        ),
        max_duration_minutes=60,
        representative=True,
    ),
    "broad": ModeConfig(
        name="broad",
        tiers=["fast", "medium", "slow"],
        priorities=["P0", "P1"],
        targets=["docker", "remote"],
        description="Broad suite — all tiers except very-slow, P0+P1 (the nightly cron's default).",
        max_duration_minutes=120,
    ),
    "full": ModeConfig(
        name="full",
        tiers=["fast", "medium", "slow", "very-slow"],
        priorities=["P0", "P1", "P2"],
        targets=["docker", "remote"],
        description="Full release validation (everything).",
        max_duration_minutes=480,
    ),
}


# Built-in mode names: these can be overridden or reset, but never deleted, so
# `--mode ci` etc. always resolve to something.
BUILTIN_MODE_NAMES = frozenset(MODES)

# Back-compat aliases: renames (dev→smoke, release→full, nightly→broad) keep the
# old names working for `--mode`, saved profiles, and saved runs. Resolved in
# get_mode_config(); not listed as selectable modes. NB: "nightly" is now only a
# schedule cadence (the cron), never a test-selection scope — the suite it runs
# is "broad".
MODE_ALIASES: dict[str, str] = {
    "dev": "smoke",
    "release": "full",
    "nightly": "broad",
    "coverage": "combo-coverage",  # pre-2026-Q2 name → combo-coverage
}


def _modes_file() -> Path:
    """Path to the user mode-overrides file ($HOP3_TEST_MODES → ~/.hop3)."""
    override = os.environ.get("HOP3_TEST_MODES")
    if override:
        return Path(override)
    return Path.home() / ".hop3" / "test-modes.toml"


def _mode_from_dict(name: str, data: dict) -> ModeConfig:
    """Build a ModeConfig from a parsed TOML table (the table key is the name)."""
    max_duration = data.get("max_duration_minutes")
    return ModeConfig(
        name=name,
        tiers=[str(t) for t in data.get("tiers", [])],
        priorities=[str(p) for p in data.get("priorities", [])],
        targets=[str(t) for t in data.get("targets", [])],
        description=str(data.get("description", "")),
        max_duration_minutes=int(max_duration) if max_duration is not None else None,
        representative=bool(data.get("representative")),
        tests=[str(t) for t in data.get("tests", [])],
    )


def _read_overrides() -> dict[str, ModeConfig]:
    """Parse the overrides file; a missing/malformed file yields no overrides."""
    path = _modes_file()
    if not path.is_file():
        return {}
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except (OSError, TOMLKitError) as e:
        logger.warning("Ignoring malformed test-modes file %s: %s", path, e)
        return {}

    overrides: dict[str, ModeConfig] = {}
    for name, data in doc.items():
        if not isinstance(data, dict):
            continue  # skip stray top-level scalars/comments
        try:
            overrides[name] = _mode_from_dict(name, data)
        except (TypeError, ValueError) as e:
            logger.warning("Ignoring bad mode %r in %s: %s", name, path, e)
    return overrides


def _write_overrides(overrides: dict[str, ModeConfig]) -> None:
    """Persist the overrides dict to the TOML file (one table per mode)."""
    path = _modes_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.document()
    doc.add(tomlkit.comment("Hop3 test-mode overrides — managed by the Test Lab UI."))
    for name in sorted(overrides):
        cfg = overrides[name]
        table = tomlkit.table()
        table["tiers"] = cfg.tiers
        table["priorities"] = cfg.priorities
        table["targets"] = cfg.targets
        table["description"] = cfg.description
        if cfg.max_duration_minutes is not None:
            table["max_duration_minutes"] = cfg.max_duration_minutes
        table["representative"] = cfg.representative
        if cfg.tests:
            table["tests"] = cfg.tests
        doc[name] = table
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def load_modes() -> dict[str, ModeConfig]:
    """Effective modes: built-in defaults overlaid with the user overrides file."""
    effective = dict(MODES)
    effective.update(_read_overrides())
    return effective


def customized_mode_names() -> set[str]:
    """Mode names that currently have an override entry in the file."""
    return set(_read_overrides())


def save_mode(name: str, config: ModeConfig) -> None:
    """Create or override a mode (built-in or custom), persisting it to the file."""
    overrides = _read_overrides()
    overrides[name] = config
    _write_overrides(overrides)


def reset_mode(name: str) -> None:
    """Drop a built-in mode's override so it reverts to the seed default."""
    if name not in BUILTIN_MODE_NAMES:
        msg = f"{name!r} is not a built-in mode; use delete_mode to remove it."
        raise ValueError(msg)
    overrides = _read_overrides()
    if overrides.pop(name, None) is not None:
        _write_overrides(overrides)


def delete_mode(name: str) -> None:
    """Remove a custom mode entirely (built-ins can only be reset, not deleted)."""
    if name in BUILTIN_MODE_NAMES:
        msg = f"Cannot delete built-in mode {name!r}; reset it instead."
        raise ValueError(msg)
    overrides = _read_overrides()
    if overrides.pop(name, None) is not None:
        _write_overrides(overrides)


def get_mode_config(mode: str) -> ModeConfig:
    """
    Get configuration for a mode (built-in or user-defined).

    Args:
        mode: Mode name (smoke, ci, curated, tag-coverage, combo-coverage,
            broad, full, a custom one, or a back-compat alias like ``dev``/
            ``release``/``nightly``/``coverage``).

    Returns:
        ModeConfig for the requested mode

    Raises:
        ValueError: If mode is not recognized
    """
    # Resolve back-compat aliases (dev→smoke, release→full) before lookup, but
    # only when the alias isn't itself a real (e.g. user-defined) mode.
    modes = load_modes()
    if mode not in modes:
        mode = MODE_ALIASES.get(mode, mode)
    if mode not in modes:
        valid_modes = ", ".join(sorted(modes))
        msg = f"Unknown mode: {mode}. Valid modes: {valid_modes}"
        raise ValueError(msg)

    return modes[mode]


def list_modes() -> list[str]:
    """Get list of available modes (built-in + user-defined), sorted."""
    return sorted(load_modes().keys())
