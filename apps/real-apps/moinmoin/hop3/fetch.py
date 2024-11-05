#!/usr/bin/env python3

import os
from pathlib import Path
from urllib.request import urlopen

VERSION = "2.0.0a1"
NAME = f"moin-{VERSION}"

DOWNLOAD_URL = f"https://github.com/moinwiki/moin/releases/download/{VERSION}/{NAME}.tar.gz"

print("We are here:", Path.cwd())

archive_path = Path("source.tar.gz")

with urlopen(DOWNLOAD_URL) as response:
    data = response.read()
    archive_path.write_bytes(data)

os.system(f"tar -xzf {archive_path}")

os.system(f"cp -r {NAME}/* .")
os.system(f"rm -rf {NAME}")
