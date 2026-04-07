#!/usr/bin/env python3
"""Validate all template-based Nix app configs.

Reads each app's hop3.toml from apps/real-apps-nix-gen/, generates
the Nix expression via the template engine, and validates it.

Modes:
    --generate   Generate .nix files only (fastest)
    --parse      Generate + nix-instantiate --parse (no network)
    --build      Generate + nix-build (slow, needs network)

Usage:
    python scripts/validate-nix-gen.py --parse
    python scripts/validate-nix-gen.py --build

Exit code 0 if all apps pass, 1 otherwise.
Suitable for CI.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

APPS_DIR = Path("apps/real-apps-nix-gen")
OUTPUT_DIR = Path("/tmp/hop3-nix-gen-validate")


def discover_apps() -> list[tuple[str, dict]]:
    """Find all apps with [nix].template in their hop3.toml."""
    apps = []
    for app_dir in sorted(APPS_DIR.iterdir()):
        toml_path = app_dir / "hop3.toml"
        if not toml_path.exists():
            continue
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        nix_config = data.get("nix", {})
        if nix_config.get("template"):
            apps.append((app_dir.name, data))
    return apps


def generate_nix(app_name: str, data: dict) -> tuple[Path, str]:
    """Generate .nix from a parsed hop3.toml. Returns (path, error)."""
    from hop3.plugins.build.nix.gen import generate
    from hop3.plugins.build.nix.gen.toml_adapter import app_spec_from_config

    nix_config = data.get("nix", {})
    metadata = data.get("metadata", {})

    spec = app_spec_from_config(nix_config, metadata, app_name)
    nix_text = generate(spec)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"{app_name}.nix"
    out.write_text(nix_text)
    return out, ""


def parse_nix(nix_file: Path) -> str:
    """Run nix-instantiate --parse. Returns error string or empty."""
    try:
        subprocess.run(
            ["nix-instantiate", "--parse", str(nix_file)],
            capture_output=True,
            check=True,
            text=True,
        )
        return ""
    except FileNotFoundError:
        return "nix-instantiate not found"
    except subprocess.CalledProcessError as e:
        return e.stderr.strip()[:200]


def build_nix(nix_file: Path) -> tuple[str, str]:
    """Run nix-build. Returns (store_path, error)."""
    try:
        proc = subprocess.run(
            ["nix-build", str(nix_file), "-A", "package", "--no-out-link"],
            capture_output=True,
            check=True,
            timeout=1800,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace")
        return stdout.strip().split("\n")[-1], ""
    except FileNotFoundError:
        return "", "nix-build not found"
    except subprocess.TimeoutExpired:
        return "", "timeout (1800s)"
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", errors="replace")
        return "", stderr.strip().split("\n")[-1][:200]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--parse", action="store_true")
    group.add_argument("--build", action="store_true")
    args = parser.parse_args()

    if not APPS_DIR.exists():
        print(f"ERROR: {APPS_DIR} not found. Run from repo root.", file=sys.stderr)
        return 1

    apps = discover_apps()
    print(f"Found {len(apps)} apps in {APPS_DIR}\n")

    results: list[tuple[str, str, str, str]] = []  # (name, template, status, note)

    for app_name, data in apps:
        template = data.get("nix", {}).get("template", "?")

        try:
            nix_file, err = generate_nix(app_name, data)
            if err:
                results.append((app_name, template, "GEN-FAIL", err))
                continue
        except Exception as e:
            results.append((app_name, template, "GEN-FAIL", str(e)[:80]))
            continue

        if args.generate:
            results.append((app_name, template, "GENERATED", ""))
            continue

        err = parse_nix(nix_file)
        if err:
            results.append((app_name, template, "PARSE-FAIL", err))
            continue

        if args.parse:
            results.append((app_name, template, "PARSED", ""))
            continue

        print(f"  Building {app_name}... ", end="", flush=True)
        store, err = build_nix(nix_file)
        if err:
            results.append((app_name, template, "BUILD-FAIL", err))
            print("FAIL")
        else:
            results.append((app_name, template, "BUILT", store))
            print(f"OK")

    # Report
    print(f"\n{'App':<22} {'Template':<20} {'Status':<12} Notes")
    print("-" * 75)
    for name, tmpl, status, note in results:
        short_note = note[:30] if note else ""
        print(f"{name:<22} {tmpl:<20} {status:<12} {short_note}")

    passed = sum(1 for r in results if "FAIL" not in r[2])
    failed = len(results) - passed
    print(f"\nTotal: {len(results)} | Passed: {passed} | Failed: {failed}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
