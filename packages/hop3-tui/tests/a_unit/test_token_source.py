# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""`hop3-tui --token` reads the token from stdin or a file, off argv."""

from __future__ import annotations

import io
import os

import pytest
from hop3_tui.__main__ import STDIN_FILENO, build_parser, read_token, reattach_terminal


def test_token_from_a_file(tmp_path):
    path = tmp_path / "token"
    path.write_text("eyJfile\n")
    assert read_token(f"@{path}", build_parser()) == "eyJfile"


def test_token_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("eyJstdin\n"))
    assert read_token("-", build_parser()) == "eyJstdin"


def test_a_literal_still_works_and_says_why_it_should_go(capsys):
    assert read_token("eyJliteral", build_parser()) == "eyJliteral"
    assert "shell history" in capsys.readouterr().err


def test_a_missing_file_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as exc:
        read_token(f"@{tmp_path / 'absent'}", build_parser())
    assert exc.value.code == 2


def test_the_terminal_goes_back_on_stdin_after_a_piped_token():
    """`pass hop3 | hop3-tui --token -` read the token, then had no terminal."""
    calls = []
    reattach_terminal(build_parser(), tty=os.devnull, dup2=lambda a, b: calls.append(b))
    assert calls == [STDIN_FILENO]


def test_no_terminal_to_reattach_is_a_usage_error_naming_the_way_out(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        reattach_terminal(build_parser(), tty=str(tmp_path / "no-tty"))
    assert exc.value.code == 2
    assert "--token @PATH" in capsys.readouterr().err
