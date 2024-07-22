from hop3_cli.main import main, parse_args


def test_args():
    args = ["debug"]
    result = parse_args(args)
    assert result.subcommand == "debug"
