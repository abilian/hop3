# Copyright (c) 2023-2024, Abilian SAS
from __future__ import annotations

from unittest import skip

from hop3_cli.main import parse_args


@skip
def test_args():
    args = ["debug"]
    result = parse_args(args)
    assert result.subcommand == "debug"
