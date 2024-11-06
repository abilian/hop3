# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from hop3.util import log

__all__ = ["found_app"]


def found_app(kind) -> None:
    """Log the detection of a specific type of app.

    Args:
    ----
        kind (str): The type of app detected.

    """
    log(f"{kind} app detected.", level=5, fg="green")
