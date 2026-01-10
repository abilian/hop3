# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test execution mode configurations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModeConfig:
    """Configuration for a test execution mode.

    Each mode defines what tests should be run based on tier,
    priority, category, and target type filters.
    """

    name: str
    """Mode name (dev, ci, nightly, release, package)."""

    tiers: list[str]
    """Allowed tiers (fast, medium, slow, very-slow)."""

    priorities: list[str]
    """Allowed priorities (P0, P1, P2)."""

    categories: list[str]
    """Allowed categories (deployment, demo, tutorial)."""

    targets: list[str]
    """Allowed target types (docker, remote, local)."""

    description: str = ""
    """Human-readable description of this mode."""

    max_duration_minutes: int | None = None
    """Expected maximum duration in minutes."""


# Pre-defined mode configurations
MODES: dict[str, ModeConfig] = {
    "dev": ModeConfig(
        name="dev",
        tiers=["fast"],
        priorities=["P0"],
        categories=["deployment"],
        targets=["docker"],
        description="Quick developer tests (fast + P0 + deployment only)",
        max_duration_minutes=5,
    ),
    "ci": ModeConfig(
        name="ci",
        tiers=["fast", "medium"],
        priorities=["P0"],
        categories=["deployment", "demo"],
        targets=["docker"],
        description="CI tests (fast+medium + P0 + deployment/demo)",
        max_duration_minutes=15,
    ),
    "nightly": ModeConfig(
        name="nightly",
        tiers=["fast", "medium", "slow"],
        priorities=["P0", "P1"],
        categories=["deployment", "demo", "tutorial"],
        targets=["docker", "remote"],
        description="Nightly tests (all tiers except very-slow, P0+P1)",
        max_duration_minutes=120,
    ),
    "release": ModeConfig(
        name="release",
        tiers=["fast", "medium", "slow", "very-slow"],
        priorities=["P0", "P1", "P2"],
        categories=["deployment", "demo", "tutorial"],
        targets=["docker", "remote"],
        description="Full release validation (everything)",
        max_duration_minutes=480,
    ),
    "package": ModeConfig(
        name="package",
        tiers=["fast", "medium", "slow"],
        priorities=["P0", "P1", "P2"],
        categories=["deployment"],
        targets=["docker", "remote"],
        description="Package validation (single package against stable Hop3)",
        max_duration_minutes=30,
    ),
}


def get_mode_config(mode: str) -> ModeConfig:
    """Get configuration for a mode.

    Args:
        mode: Mode name (dev, ci, nightly, release, package)

    Returns:
        ModeConfig for the requested mode

    Raises:
        ValueError: If mode is not recognized
    """
    if mode not in MODES:
        valid_modes = ", ".join(MODES.keys())
        msg = f"Unknown mode: {mode}. Valid modes: {valid_modes}"
        raise ValueError(msg)

    return MODES[mode]


def list_modes() -> list[str]:
    """Get list of available modes.

    Returns:
        List of mode names
    """
    return list(MODES.keys())
