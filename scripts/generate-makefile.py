#!/usr/bin/env python3

import re
import subprocess
from io import StringIO
from pathlib import Path

from devtools import debug


def main():
    output = StringIO()

    makefile_path = Path("Makefile")

    orig_makefile = makefile_path.read_text().strip()
    orig_makefile = orig_makefile.split("# Delegate to just")[0].strip()

    makefile_targets = []
    for line in orig_makefile.split("\n"):
        m = re.match(r"(\S+):", line)
        if m:
            makefile_targets.append(m.group(1))

    just_recipes = subprocess.check_output(["just", "--list"]).decode("utf-8")
    recipes = just_recipes.split("\n")
    for line in recipes:
        if not line.startswith(" "):
            continue

        line = line.strip()
        m = re.match(r"(\S+)\s*(.*)", line)
        recipe_name = m.group(1)
        recipe_help = m.group(2)
        if recipe_help.startswith("#"):
            recipe_help = recipe_help[1:].strip()

        if recipe_name in makefile_targets:
            continue

        if recipe_help:
            output.write(f"## {recipe_help}\n")
        output.write(f"{recipe_name}:\n")
        output.write(f"\tjust {recipe_name}\n\n")

    makefile_path.write_text(
        f"{orig_makefile}\n\n# Delegate to just\n\n{output.getvalue()}")


if __name__ == "__main__":
    main()
