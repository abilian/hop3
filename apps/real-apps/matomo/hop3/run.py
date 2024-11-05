#!/usr/bin/env python3
from __future__ import annotations

import os

PORT = os.getenv("PORT", "8080")

os.chdir("matomo")
os.system(f"php -S 0.0.0.0:{PORT}")
