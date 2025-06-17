#!/usr/bin/env python3

import shutil
import sys

r = shutil.which("python3")
if not r:
    print("Python3 not found.")
    sys.exit(1)

r = shutil.which("python")
if not r:
    print("`python` executable not found. We found `python`.")
    sys.exit(1)

r = shutil.which("uv")
if not r:
    print("UV not found. Install it with `brew install uv` or ...")
    sys.exit(1)

r = shutil.which("poetry")
if not r:
    print("Poetry not found. Install it with `uv tool install poetry`.")
    sys.exit(1)

r = shutil.which("nox")
if not r:
    print("Nox not found. Install it with `uv tool install nox`.")
    sys.exit(1)

r = shutil.which("make")
if not r:
    print("Make not found.")
    sys.exit(1)

r = shutil.which("just")
if not r:
    print("Just not found. Install it with `brew install just` or `cargo install just`.")
    sys.exit(1)

print("All good.")
