"""Command-line interface for the spike.

Usage:
    hop3-nix-gen <app-name>          Print generated hop3.nix to stdout
    hop3-nix-gen --list              List available specs
"""

from __future__ import annotations

import sys

from hop3_nix_gen.registry import generate
from hop3_nix_gen.specs import SPECS


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        _print_usage()
        return 0

    if sys.argv[1] == "--list":
        for name in sorted(SPECS):
            spec = SPECS[name]
            print(f"{name:20s}  {spec.template:20s}  {spec.description}")
        return 0

    app_name = sys.argv[1]
    if app_name not in SPECS:
        available = ", ".join(sorted(SPECS))
        print(f"Unknown app: {app_name}", file=sys.stderr)
        print(f"Available: {available}", file=sys.stderr)
        return 1

    print(generate(SPECS[app_name]), end="")
    return 0


def _print_usage() -> None:
    print(__doc__, file=sys.stderr)
    print("", file=sys.stderr)
    print("Available apps:", file=sys.stderr)
    for name in sorted(SPECS):
        print(f"  {name}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
