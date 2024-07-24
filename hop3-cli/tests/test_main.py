# Copyright (c) 2023-2024, Abilian SAS

from hop3_cli.main import parse_args


def test_args():
    args = ["debug"]
    result = parse_args(args)
    assert result.subcommand == "debug"
