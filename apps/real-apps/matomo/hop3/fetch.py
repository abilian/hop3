#!/usr/bin/env python3

import os
from pathlib import Path
from urllib.request import urlopen

DOWNLOAD_URL = "https://builds.matomo.org/matomo-5.0.3.zip"

print("We are here:", Path.cwd())

with urlopen(DOWNLOAD_URL) as response:
    data = response.read()
    archive_path = Path('matomo.zip')
    archive_path.write_bytes(data)

os.system(f"unzip -o {archive_path} -d {Path.cwd()}")
