#!/usr/bin/env python3
"""Validate all specs by generating and optionally building them with nix.

Usage:
    python scripts/validate_all.py --generate   # Just generate .nix files
    python scripts/validate_all.py --parse      # Generate + nix-instantiate --parse
    python scripts/validate_all.py --build      # Generate + nix-build (slow!)

The generated files are written to ./output/ (git-ignored).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Make the package importable when running this script directly
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hop3_nix_gen.registry import generate  # noqa: E402
from hop3_nix_gen.specs import SPECS  # noqa: E402


@dataclass
class Result:
    app: str
    template: str
    generated: bool = False
    parsed: bool = False
    built: bool = False
    error: str = ""

    @property
    def status(self) -> str:
        if self.error:
            return "FAIL"
        if self.built:
            return "BUILT"
        if self.parsed:
            return "PARSED"
        if self.generated:
            return "GENERATED"
        return "NOT RUN"


def cmd_generate(output_dir: Path) -> list[Result]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[Result] = []

    for name, spec in sorted(SPECS.items()):
        result = Result(app=name, template=spec.template)
        try:
            nix_text = generate(spec)
            out_file = output_dir / f"{name}.nix"
            out_file.write_text(nix_text)
            result.generated = True
        except Exception as e:
            result.error = f"generate: {e}"
        results.append(result)

    return results


def cmd_parse(output_dir: Path) -> list[Result]:
    results = cmd_generate(output_dir)
    for result in results:
        if not result.generated:
            continue
        nix_file = output_dir / f"{result.app}.nix"
        try:
            subprocess.run(
                ["nix-instantiate", "--parse", str(nix_file)],
                capture_output=True,
                check=True,
                text=True,
            )
            result.parsed = True
        except FileNotFoundError:
            result.error = "parse: nix-instantiate not found in PATH"
        except subprocess.CalledProcessError as e:
            result.error = f"parse: {e.stderr.strip()[:200]}"
    return results


def cmd_build(output_dir: Path) -> list[Result]:
    results = cmd_parse(output_dir)
    for result in results:
        if not result.parsed:
            continue
        nix_file = output_dir / f"{result.app}.nix"
        print(f"  Building {result.app}... ", end="", flush=True)
        try:
            proc = subprocess.run(
                [
                    "nix-build",
                    str(nix_file),
                    "-A",
                    "package",
                    "--no-out-link",
                ],
                capture_output=True,
                check=True,
                text=True,
                timeout=600,
            )
            result.built = True
            # Extract the store path from stdout
            store_path = proc.stdout.strip().split("\n")[-1]
            print(f"OK ({store_path})")
        except FileNotFoundError:
            result.error = "build: nix-build not found in PATH"
            print("FAIL (nix-build missing)")
        except subprocess.TimeoutExpired:
            result.error = "build: timeout after 600s"
            print("FAIL (timeout)")
        except subprocess.CalledProcessError as e:
            stderr_tail = (e.stderr or "").strip().split("\n")[-5:]
            result.error = "build: " + " | ".join(stderr_tail)[:400]
            print("FAIL")
            print(f"    {result.error}")
    return results


def print_report(results: list[Result]) -> None:
    print()
    print("=" * 70)
    print(f"{'App':<15} {'Template':<20} {'Status':<10} {'Notes'}")
    print("-" * 70)
    for r in results:
        notes = r.error if r.error else ""
        print(f"{r.app:<15} {r.template:<20} {r.status:<10} {notes[:25]}")
    print("=" * 70)

    total = len(results)
    generated = sum(1 for r in results if r.generated)
    parsed = sum(1 for r in results if r.parsed)
    built = sum(1 for r in results if r.built)
    print(f"Total: {total} | Generated: {generated} | Parsed: {parsed} | Built: {built}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--generate", action="store_true", help="Generate .nix files only"
    )
    group.add_argument(
        "--parse", action="store_true", help="Generate + nix-instantiate --parse"
    )
    group.add_argument("--build", action="store_true", help="Generate + nix-build")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "output",
        help="Output directory for generated .nix files",
    )
    args = parser.parse_args()

    print(f"Output directory: {args.output}")
    print(f"Specs to process: {len(SPECS)}")
    print()

    if args.generate:
        results = cmd_generate(args.output)
    elif args.parse:
        results = cmd_parse(args.output)
    else:
        results = cmd_build(args.output)

    print_report(results)

    # Exit code: 0 if all succeeded, 1 otherwise
    if args.build:
        ok = all(r.built for r in results)
    elif args.parse:
        ok = all(r.parsed for r in results)
    else:
        ok = all(r.generated for r in results)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
