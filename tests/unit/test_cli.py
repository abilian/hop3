from __future__ import annotations

from hop3.main import main


def test_cli():
    try:
        main(["help"])
    except SystemExit as e:
        assert e.code == 0
