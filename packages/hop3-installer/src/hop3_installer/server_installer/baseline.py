# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Derive the installer package baseline from the app catalogue.

The native-build-profile contract:

1. Each native-profile app declares its host-level needs in
   `[build].packages` + `[run].packages` of its `hop3.toml`. These are
   **declarations**, not install triggers.
2. At server-provisioning time (not deploy time), the installer unions
   those declarations across the whole catalogue and installs the
   result. This module computes that union; `installer.py` wires the
   apt/dnf call.
3. The union uses canonical (Debian) names; `package_aliases.py`
   translates to the local OS family right before install.

This is a pure library: no subprocess calls, no apt invocations. That
makes it cheap to test and re-runnable as a CI check ("the committed
baseline has not drifted from the catalogue").
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import tomllib

from .package_aliases import PACKAGE_ALIASES, supported_os_families

# Node.js, its dev headers, npm and node-gyp are provided by the NodeSource
# toolchain (installed separately in deps_{debian,fedora}). Letting the distro's
# equivalents into the apt/dnf baseline makes the package manager try to install
# Debian's nodejs alongside NodeSource's — an unsatisfiable conflict ("held
# broken packages") that aborts the *entire* baseline and leaves Node broken, so
# every Node app then fails to find node/npm/nodeenv. node-gyp downloads the
# matching headers itself, so dropping libnode-dev costs us nothing. These are
# canonical (Debian-ish) names, matched before OS translation.
NODESOURCE_PROVIDED: frozenset[str] = frozenset({
    "nodejs",
    "npm",
    "node-gyp",
    "libnode-dev",
})


@dataclass(frozen=True, slots=True)
class BaselineSource:
    """Where one package came from in the catalogue."""

    package: str
    app: str
    field: str  # "build" or "run"


@dataclass(frozen=True, slots=True)
class BaselineResult:
    """Derived baseline: the union of declared packages, plus traceability."""

    # Canonical (Debian) names, sorted and deduplicated.
    canonical: tuple[str, ...]
    # Per-OS-family lists (also sorted + deduped; None entries dropped).
    by_os_family: dict[str, tuple[str, ...]]
    # Every declaration that fed into the union — useful for
    # diagnostic output ("why is libbrotli-dev in here?").
    sources: tuple[BaselineSource, ...]
    # Packages declared but missing from package_aliases.py. These are
    # ignored with a warning at install time, but surfaced here so CI
    # can fail on drift.
    unknown: tuple[str, ...]


def derive_baseline(app_dirs: list[Path]) -> BaselineResult:
    """
    Walk hop3.toml files, union declarations, return the baseline.

    Args:
        app_dirs: Directories to scan recursively for hop3.toml.
            Typically `[Path("../hop3-catalog/apps")]`, scanned recursively,
            so recipes at every maturity are included — an unverified or broken
            app's declarations still seed the baseline, which is what makes a
            retry installable.

    Returns:
        BaselineResult describing the canonical union, per-OS
        translations, source attribution, and any unknown packages.
    """
    sources: list[BaselineSource] = []
    for app_dir in app_dirs:
        for toml_path in sorted(app_dir.rglob("hop3.toml")):
            sources.extend(_read_declarations(toml_path))

    canonical = tuple(
        p for p in sorted({s.package for s in sources}) if p not in NODESOURCE_PROVIDED
    )
    unknown = tuple(p for p in canonical if p not in PACKAGE_ALIASES)

    by_family: dict[str, tuple[str, ...]] = {}
    for family in supported_os_families():
        translated = {
            PACKAGE_ALIASES[pkg][family]
            for pkg in canonical
            if pkg in PACKAGE_ALIASES and PACKAGE_ALIASES[pkg][family] is not None
        }
        by_family[family] = tuple(sorted(translated))  # type: ignore[arg-type]

    return BaselineResult(
        canonical=canonical,
        by_os_family=by_family,
        sources=tuple(sources),
        unknown=unknown,
    )


def _read_declarations(toml_path: Path) -> list[BaselineSource]:
    """Extract `[build].packages` + `[run].packages` from one hop3.toml."""
    app_name = toml_path.parent.name
    try:
        data = tomllib.loads(toml_path.read_text())
    except tomllib.TOMLDecodeError:
        # Malformed hop3.toml — leave it out of the baseline rather
        # than crashing the installer. CI should catch the TOML error
        # separately.
        return []

    out: list[BaselineSource] = []
    for field in ("build", "run"):
        packages = data.get(field, {}).get("packages", [])
        for pkg in packages:
            if isinstance(pkg, str):
                out.append(BaselineSource(package=pkg, app=app_name, field=field))
    return out


def format_baselines_module(result: BaselineResult) -> str:
    """
    Format a BaselineResult as a Python module with a dict constant.

    Output is `baselines.py` — a module committed to the repo,
    imported by the installer at provisioning time, and picked up
    verbatim by the single-file bundler (so no data-file I/O needed in
    the curl|python install path). Regeneration after catalogue
    changes is tracked by CI via `--check`.
    """
    # Build the SPDX header from parts so the REUSE tool doesn't read this
    # generator module as being licensed by the identifier string it emits.
    spdx_license_identifier = "SPDX-License-Identifier"
    license = "Apache-2.0"
    header = (
        "# Copyright (c) 2025-2026, Abilian SAS\n"
        f"# {spdx_license_identifier}: {license}\n"
        '"""Catalogue-derived installer baselines, per OS family.\n\n'
        "GENERATED FROM the catalog's apps/<status>/*/hop3.toml by\n"
        "`python -m hop3_installer.server_installer.baseline`.\n"
        "Do not edit by hand. Regenerate after catalogue changes.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
    )
    body = "BASELINE_PACKAGES: dict[str, list[str]] = {\n"
    for family in sorted(result.by_os_family.keys()):
        packages = result.by_os_family[family]
        body += f'    "{family}": [\n'
        for pkg in packages:
            body += f'        "{pkg}",\n'
        body += "    ],\n"
    body += "}\n"
    return header + body


def main() -> int:
    """
    CLI: regenerate baselines.py from the catalogue.

    Called as `python -m hop3_installer.server_installer.baseline`.
    Writes to `packages/hop3-installer/src/hop3_installer/server_installer/baselines.py`.
    Use `--check` in CI to fail on drift without writing.
    """
    parser = argparse.ArgumentParser(
        description="Regenerate Hop3 installer baselines from catalogue."
    )
    parser.add_argument(
        "--apps-dir",
        type=Path,
        action="append",
        default=None,
        help=(
            "Directory to scan for hop3.toml (can repeat). "
            "Defaults to the sibling catalog checkout (all maturities)."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if generated output differs from the committed file.",
    )
    args = parser.parse_args()

    if args.apps_dir is None:
        # The catalog holds every recipe now, at every maturity. The baseline
        # wants them ALL — including `alpha` and `broken`, whose declarations
        # seed it so a retry is installable, which is what the old
        # `apps/bad/...` entry was for.
        args.apps_dir = [Path("../hop3-catalog/apps")]

    result = derive_baseline(args.apps_dir)

    if result.unknown:
        print(
            "WARNING: packages declared in catalogue but missing from "
            f"package_aliases.py: {result.unknown}",
            file=sys.stderr,
        )

    out_file = Path(__file__).parent / "baselines.py"
    text = format_baselines_module(result)

    if args.check:
        existing = out_file.read_text() if out_file.exists() else ""
        if existing != text:
            print(
                f"DRIFT: {out_file} is out of sync with catalogue. "
                "Regenerate with "
                "`python -m hop3_installer.server_installer.baseline`.",
                file=sys.stderr,
            )
            return 1
        return 0

    out_file.write_text(text)
    totals = ", ".join(
        f"{fam}={len(pkgs)}" for fam, pkgs in sorted(result.by_os_family.items())
    )
    print(f"Wrote {out_file} ({totals})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
