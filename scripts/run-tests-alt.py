#!/usr/bin/env python3

# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-License-Identifier: MIT

import subprocess
from pathlib import Path


def main():
    for test_dir in sorted(Path("apps/test-apps").iterdir()):
        if not test_dir.is_dir():
            continue

        run_test(test_dir)


def run_test(test_dir):
    print(f"Testing {test_dir}")
    shell(f"hop-test -a {test_dir}")


def shell(cmd):
    print(f"$ {cmd}")
    return subprocess.run(cmd, shell=True, check=True, capture_output=True)


if __name__ == "__main__":
    main()
