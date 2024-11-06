#!/usr/bin/env python3

import re
import subprocess
from pathlib import Path

from devtools import debug


def main():
    makefile = Path("Makefile").open("w")
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
        debug(recipe_name, recipe_help)
        if recipe_help:
            makefile.write(f"## {recipe_help}\n")
        makefile.write(f"{recipe_name}:\n")
        makefile.write(f"\tjust {recipe_name}\n\n")


if __name__ == "__main__":
    main()
