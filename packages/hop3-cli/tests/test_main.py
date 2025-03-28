# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from unittest import skip

# from hop3_cli.new import parse_args


@skip
def test_args() -> None:
    args = ["debug"]
    result = parse_args(args)
    assert result.subcommand == "debug"
