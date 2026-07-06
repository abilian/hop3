# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Module entry point so `python -m hop3_testing.cli` works (PATH-independent).

The image sweep (`run --images`) spawns one `python -m hop3_testing.cli run
--provider hetzner --image X` per image, using the same interpreter rather than
relying on the `hop3-test` console script being on PATH.
"""

from __future__ import annotations

from hop3_testing.cli import main

if __name__ == "__main__":
    main()
