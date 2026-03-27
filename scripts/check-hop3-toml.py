#!/usr/bin/env python3
# Copyright (c) 2023-2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Validate hop3.toml files against the schema.

Usage:
    python scripts/check-hop3-toml.py apps/*/hop3.toml demos/*/app/hop3.toml
    python scripts/check-hop3-toml.py $(find . -name hop3.toml)
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def check_file(path: Path) -> list[str]:
    """Validate a single hop3.toml file.

    Returns list of error strings (empty if valid).
    """
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        return [f"Invalid TOML: {e}"]

    try:
        validate_hop3_toml(data)
        return []
    except Hop3TomlValidationError as e:
        return [str(e)]


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <hop3.toml> [hop3.toml ...]", file=sys.stderr)
        return 2

    paths = [Path(arg) for arg in sys.argv[1:]]
    total = 0
    failed = 0

    for path in paths:
        if not path.exists():
            print(f"SKIP {path} (not found)")
            continue

        total += 1
        errors = check_file(path)
        if errors:
            failed += 1
            print(f"FAIL {path}")
            for err in errors:
                for line in err.splitlines():
                    print(f"     {line}")
        else:
            print(f"  OK {path}")

    print(f"\n{total} files checked, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
