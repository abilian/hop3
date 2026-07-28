#!/usr/bin/env python3
"""
Regenerate schema/hop3.toml.schema.json from the Pydantic models.

Run after changing hop3.toml's schema. A test (test_json_schema.py) fails if the
committed file is stale, so this is never something you can forget silently.

    uv run scripts/generate-toml-schema.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from hop3.project.json_schema import SCHEMA_URL, build_json_schema

REPO = Path(__file__).resolve().parent.parent
OUTPUT = REPO / "schema" / "hop3.toml.schema.json"


def published_path(site_dir: Path) -> Path:
    """
    Where the schema must land inside the built docs site.

    Derived from SCHEMA_URL rather than written out again, so the file the site
    serves is always the one a recipe's `#:schema` directive asks for. Spelling
    it twice is how a published schema quietly 404s.
    """
    return site_dir / urlparse(SCHEMA_URL).path.lstrip("/")


def render() -> str:
    """The exact bytes the committed file must contain."""
    # sort_keys so an unrelated reordering inside Pydantic cannot produce a
    # spurious diff, and a trailing newline so the file is POSIX-clean.
    return json.dumps(build_json_schema(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site-dir",
        type=Path,
        help=(
            "also copy the schema into a built docs site, at the path "
            "SCHEMA_URL points to (used by docs/Makefile at build time)"
        ),
    )
    args = parser.parse_args()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    content = render()
    previous = OUTPUT.read_text() if OUTPUT.exists() else ""
    OUTPUT.write_text(content)
    print(f"{'unchanged' if content == previous else 'regenerated'}: {OUTPUT}")

    if args.site_dir:
        target = published_path(args.site_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        print(f"published: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
