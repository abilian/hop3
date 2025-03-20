#!/usr/bin/env python3

# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess


def main() -> None:
    cmd = "ssh root@ssh.hop.abilian.com rm -rf /home/hop3"
    subprocess.run(cmd, shell=True, check=True)

    cmd = "make deploy-dev"
    subprocess.run(cmd, shell=True, check=True)

    cmd = "hop-test --ff"
    subprocess.run(cmd, shell=True, check=True)


if __name__ == "__main__":
    main()
