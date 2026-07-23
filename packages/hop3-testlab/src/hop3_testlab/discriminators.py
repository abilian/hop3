# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Display discriminators derived from a test's canonical name.

A test's name is its path relative to the repo root (set by the catalog
scanner), e.g. ``apps/real-apps-docker/bugsink``. That path already encodes
the packaging *variant* (docker / native / nix / nix-template) and the short
app name — the run report uses both as sort/filter discriminators.
"""

from __future__ import annotations

# Order matters: "real-apps-nix-gen" must be tested before "real-apps-nix"
# (substring), and the "*-bad" negative-test dirs carry the flavor too
# (e.g. real-apps-native-bad -> native), which the substring match handles.
_VARIANT_RULES: tuple[tuple[str, str], ...] = (
    ("real-apps-nix-gen", "nix-template"),
    ("real-apps-nix", "nix"),
    ("real-apps-native", "native"),
    ("real-apps-docker", "docker"),
    ("test-apps-nix", "nix"),
    ("test-apps-procfile", "procfile"),
    ("internal-apps", "internal"),
    ("sandbox", "sandbox"),
)


def variant_of(test_name: str | None) -> str:
    """Classify a test by packaging variant from its path-based name."""
    if not test_name:
        return "other"
    name = test_name.replace("\\", "/")
    for needle, label in _VARIANT_RULES:
        if needle in name:
            return label
    if name.startswith("demos/") or "/demos/" in name:
        return "demo"
    if "tutorials" in name or name.startswith("docs/"):
        return "tutorial"
    return "other"


def type_of(test_name: str | None) -> str:
    """
    Classify a test as one of the three run types: app / demo / tutorial.

    Path-based, matching how the engine counts planned tests per type
    (``_count_by_type``), so live "done / planned" lines up per type.
    """
    name = (test_name or "").replace("\\", "/")
    if name.startswith("demos/") or "/demos/" in name:
        return "demo"
    if "tutorials" in name or name.startswith("docs/"):
        return "tutorial"
    return "app"


# Generic container dirs that aren't a useful display name on their own: a demo
# packaged at demos/demo15/app should show as "demo15", not "app". Mirrors the
# catalog's _derive_unique_name, which avoids the same generic leaves.
_GENERIC_LEAVES = frozenset({"app", "src", "web", "server", "application", "site"})


def short_app(test_name: str | None) -> str:
    """
    The display name of a path-based test name (``bugsink``).

    Skips a generic container leaf (``app``/``src``/…) in favour of its parent,
    so ``demos/demo15/app`` shows as ``demo15`` — otherwise every demo's app
    subdir collapses to the indistinguishable ``app``.
    """
    if not test_name:
        return "—"
    parts = [p for p in test_name.replace("\\", "/").rstrip("/").split("/") if p]
    while len(parts) > 1 and parts[-1].lower() in _GENERIC_LEAVES:
        parts.pop()
    return parts[-1] if parts else "—"
