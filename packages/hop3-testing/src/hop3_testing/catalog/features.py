# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Derive the installer ``--with`` features a selected app set requires.

Apps declare their addons in ``hop3.toml`` under ``[[addons]].type``, surfaced as
``TestDefinition.requirements.services``. The server must be installed with those
addons or the app's addon provisioning fails at deploy time with the opaque
"Was the server installed with '--with s3'?". Rather than make the operator hand-
pass ``--with s3`` (a manual workaround) or silently skip the app (a silent
skip), the framework installs what the selected apps declare.

This module is the single source of truth mapping an addon ``type`` to an
installer feature name, and the union over a selection. It depends only on the
catalog models, so both the ``run`` path (cli/) and the cloud path
(system_tests/) can import it without a cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_testing.exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from hop3_testing.catalog.models import TestDefinition

# addon `type` (hop3.toml) -> installer --with feature name. Identity for
# docker/mysql/redis/s3/nix/rust; only postgres needs an alias.
_ADDON_FEATURE_ALIASES = {"postgres": "postgresql"}

# Features the server installer's --with understands (ADR 052 D4). An addon that
# maps to nothing here is a real platform gap — surface it, don't drop it.
KNOWN_INSTALLER_FEATURES = frozenset({
    "docker",
    "mysql",
    "redis",
    "postgresql",
    "s3",
    "nix",
    "rust",
    # `--with email` installs Postfix inert (ADR 054); the app's email addon
    # then inherits whatever backend the operator configures, and degrades to
    # no outbound mail when none is set. Kept in sync with the installer's
    # `ServerConfig.with_*` properties — see test_every_declared_addon_is_provisionable.
    "email",
})


def feature_for_addon(addon_type: str) -> str:
    """Map an app addon ``type`` to the installer ``--with`` feature name."""
    return _ADDON_FEATURE_ALIASES.get(addon_type, addon_type)


def required_features_from_tests(tests: Iterable[TestDefinition]) -> set[str]:
    """Union of installer features the selected apps' declared addons require."""
    return {feature_for_addon(svc) for t in tests for svc in t.requirements.services}


def merge_features(base: Iterable[str], extra: Iterable[str]) -> list[str]:
    """
    Order-stable union: everything in ``base`` first, then unseen ``extra``.

    ``all`` is the installer's install-everything sentinel — it subsumes every
    specific feature. When it is present the result collapses to just ``["all"]``
    rather than a redundant ``all,postgresql,mysql`` (e.g. ``--with all`` plus the
    addons the selected apps declare).
    """
    out = list(base)
    seen = set(out)
    for feat in extra:
        if feat not in seen:
            out.append(feat)
            seen.add(feat)
    if "all" in seen:
        return ["all"]
    return out


def features_for_suites(project_root: Path, suites: Iterable[str]) -> set[str]:
    """
    Required installer features for the apps under the given suite paths.

    For the cloud path, which holds only suite path strings (not resolved
    TestDefinitions): scan the catalog and union each app's declared addons.
    Fail loud on a scan/validation error — a caller must NOT swallow this and
    silently deploy defaults.
    """
    from hop3_testing.catalog.scanner import (  # ruff:ignore[import-outside-top-level]
        Catalog,
    )

    paths = list(suites)
    if not paths:
        return set()
    catalog = Catalog(project_root)
    catalog.scan(paths=paths)
    required = required_features_from_tests(catalog.all_tests())
    validate_features(required)
    return required


def validate_features(features: Iterable[str]) -> None:
    """
    Abort loudly if a required feature has no installer support.

    Silently dropping an unprovisionable addon (or passing it to the installer as
    garbage) would resurface as the opaque "Was the server installed with
    '--with X'?" failure — surface the platform gap instead.
    """
    unknown = sorted(f for f in features if f not in KNOWN_INSTALLER_FEATURES)
    if unknown:
        msg = (
            f"Selected apps require addon(s) with no installer feature: {unknown}. "
            f"Add installer --with support, or a mapping in catalog/features.py."
        )
        raise ConfigurationError(msg)
