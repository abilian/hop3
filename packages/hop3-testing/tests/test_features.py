# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The deploy must install the addons the selected apps DECLARE.

Bug: `hop3-test run .../150-flask-s3` deployed the server without
s3, so the app's s3 addon couldn't be provisioned ("Was the server installed
with '--with s3'?"). The framework already knows the app needs s3 (hop3.toml
[[addons]] type="s3"); these pin that it now unions those addons into the deploy
--with features — no manual --with, no silently-skipped app.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from hop3_testing.catalog.features import (
    KNOWN_INSTALLER_FEATURES,
    feature_for_addon,
    features_for_suites,
    merge_features,
    required_features_from_tests,
    validate_features,
)
from hop3_testing.exceptions import ConfigurationError

# tests/ -> hop3-testing -> packages -> repo root
REPO = Path(__file__).resolve().parents[3]
S3_APP = "apps/test-apps-procfile/150-flask-s3"


def _t(*services):
    return SimpleNamespace(requirements=SimpleNamespace(services=list(services)))


def test_required_features_unions_services():
    assert required_features_from_tests([_t("s3"), _t("redis")]) == {"s3", "redis"}


def test_postgres_addon_normalized_to_postgresql():
    assert required_features_from_tests([_t("postgres")]) == {"postgresql"}
    assert feature_for_addon("postgres") == "postgresql"
    assert feature_for_addon("s3") == "s3"  # identity otherwise


def test_no_declared_addons_means_no_extra_features():
    assert required_features_from_tests([_t()]) == set()


def test_merge_features_is_order_stable_union():
    assert merge_features(["docker", "mysql"], ["mysql", "s3"]) == [
        "docker",
        "mysql",
        "s3",
    ]


def test_merge_features_collapses_all_sentinel():
    # `--with all` + apps declaring postgres/mysql must NOT become
    # `all,postgresql,mysql` — `all` already subsumes them.
    assert merge_features(["all"], ["postgresql", "mysql"]) == ["all"]
    assert merge_features(["docker"], ["all"]) == ["all"]
    # No `all` → normal union, unchanged.
    assert merge_features(["nix"], ["postgresql"]) == ["nix", "postgresql"]


def test_validate_aborts_on_unprovisionable_addon():
    # An addon with no installer feature is a platform gap — fail loud, don't drop.
    with pytest.raises(ConfigurationError):
        validate_features({"quantum-db"})
    validate_features({"s3", "postgresql", "docker"})  # known -> no raise


def test_features_for_suites_derives_s3_from_the_real_app():
    # The exact bug scenario, resolved from the app's hop3.toml on disk.
    assert "s3" in features_for_suites(REPO, [S3_APP])


def test_email_addon_maps_to_the_installer_feature():
    """
    `--with email` exists in the installer; the map must know it.

    Regression: bugsink declares `[[addons]] type = "email"`, and because this
    set omitted "email" every run selecting it aborted with "addon(s) with no
    installer feature", even though the installer supports `--with email`.
    """
    assert feature_for_addon("email") == "email"
    validate_features({"email"})  # must not raise


def test_every_declared_addon_is_provisionable():
    """
    No app may declare an addon the harness cannot install.

    This is the drift guard: an addon added to a recipe without a matching
    installer feature fails here, at test time, instead of aborting a cloud run
    after the server has already been provisioned.
    """
    root = REPO / "apps"
    assert root.is_dir(), f"app corpus not found at {root}"
    declared: dict[str, set[str]] = {}
    for toml_path in root.glob("*/*/hop3.toml"):
        for addon in re.findall(
            r'^\s*type\s*=\s*"([^"]+)"', toml_path.read_text(), re.MULTILINE
        ):
            declared.setdefault(addon, set()).add(toml_path.parent.name)

    assert declared, f"no addons found under {root} — glob likely wrong"
    unprovisionable = {
        addon: sorted(apps)
        for addon, apps in declared.items()
        if feature_for_addon(addon) not in KNOWN_INSTALLER_FEATURES
    }
    assert unprovisionable == {}, (
        f"apps declare addons with no installer feature: {unprovisionable}"
    )
