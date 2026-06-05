# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Tests for CLI-override handling in system_tests.config.

Regression focus: the `--with` feature override must UNION onto the
baseline (docker/mysql/postgresql) rather than replace it, and must
survive being applied alongside other overrides (branch, use_local_repo)
— which previously silently reset `features` to the default. This is the
gap that left `hop3-test cloud` unable to install redis for apps like
bookwyrm (which needs postgres AND redis).
"""

from __future__ import annotations

from hop3_testing.system_tests.config import Config, _apply_overrides


def _base() -> Config:
    """A Config with default deployment features (docker/mysql/postgresql)."""
    return Config.from_dict({})


def test_with_unions_onto_baseline() -> None:
    """`--with redis` adds redis without dropping the baseline addons."""
    cfg = _apply_overrides(_base(), {"features": ["redis"]})
    assert cfg.deployment.features == ["docker", "mysql", "postgresql", "redis"]


def test_with_multiple_features() -> None:
    cfg = _apply_overrides(_base(), {"features": ["redis", "nix"]})
    assert cfg.deployment.features == [
        "docker",
        "mysql",
        "postgresql",
        "redis",
        "nix",
    ]


def test_with_dedups_already_present_feature() -> None:
    """Requesting a baseline feature again is a no-op (no duplicate)."""
    cfg = _apply_overrides(_base(), {"features": ["mysql", "redis"]})
    assert cfg.deployment.features == ["docker", "mysql", "postgresql", "redis"]


def test_features_survive_use_local_repo_override() -> None:
    """The use_local_repo rebuild must not clobber a requested feature.

    Both overrides arrive together in the real `hop3-test cloud
    --use-local-repo --with redis` path; the redis must persist.
    """
    cfg = _apply_overrides(_base(), {"use_local_repo": True, "features": ["redis"]})
    assert cfg.deployment.use_local_repo is True
    assert "redis" in cfg.deployment.features
    assert "postgresql" in cfg.deployment.features


def test_features_survive_branch_override() -> None:
    cfg = _apply_overrides(_base(), {"branch": "feat/x", "features": ["redis"]})
    assert cfg.deployment.branch == "feat/x"
    assert "redis" in cfg.deployment.features


def test_no_features_override_leaves_baseline() -> None:
    cfg = _apply_overrides(_base(), {"use_local_repo": True})
    assert cfg.deployment.features == ["docker", "mysql", "postgresql"]


def test_branch_override_no_longer_resets_features() -> None:
    """Regression: a config-file feature set must survive a branch override.

    Previously the branch rebuild dropped `features`, silently resetting
    a custom set back to the default.
    """
    base = Config.from_dict({"deployment": {"features": ["docker", "redis"]}})
    cfg = _apply_overrides(base, {"branch": "feat/x"})
    assert cfg.deployment.features == ["docker", "redis"]
