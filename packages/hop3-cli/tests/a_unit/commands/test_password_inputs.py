# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for --password-file / --stdin handling on user commands (ADR 036 §D14)."""

from __future__ import annotations

import io
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from hop3_cli.commands.arguments import (
    _resolve_env_set_values,
    _resolve_flag_value_sources,
    _resolve_password_inputs,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_user_add_with_password_file(tmp_path: Path) -> None:
    pw_file = tmp_path / "pw.txt"
    pw_file.write_text("s3cret\n", encoding="utf-8")

    args = [
        "user",
        "add",
        "alice",
        "alice@example.com",
        "--password-file",
        str(pw_file),
    ]
    _resolve_password_inputs(args)

    assert args == ["user", "add", "alice", "alice@example.com", "s3cret"]


def test_user_add_with_password_file_equals_form(tmp_path: Path) -> None:
    pw_file = tmp_path / "pw.txt"
    pw_file.write_text("s3cret", encoding="utf-8")

    args = ["user", "add", "alice", "alice@example.com", f"--password-file={pw_file}"]
    _resolve_password_inputs(args)

    assert args == ["user", "add", "alice", "alice@example.com", "s3cret"]


def test_user_set_password_with_password_file(tmp_path: Path) -> None:
    pw_file = tmp_path / "pw.txt"
    pw_file.write_text("newpw", encoding="utf-8")

    args = ["user", "set-password", "alice", "--password-file", str(pw_file)]
    _resolve_password_inputs(args)

    assert args == ["user", "set-password", "alice", "newpw"]


def test_password_file_dash_means_stdin() -> None:
    args = ["user", "add", "alice", "alice@example.com", "--password-file", "-"]
    fake_stdin = io.StringIO("from-stdin\n")
    with (
        patch.object(sys, "stdin", fake_stdin),
        patch.object(sys.stdin, "isatty", lambda: False, create=True),
    ):
        _resolve_password_inputs(args)
    assert args[-1] == "from-stdin"


def test_stdin_flag_reads_from_stdin() -> None:
    args = ["user", "set-password", "alice", "--stdin"]
    fake_stdin = io.StringIO("piped\n")
    with (
        patch.object(sys, "stdin", fake_stdin),
        patch.object(sys.stdin, "isatty", lambda: False, create=True),
    ):
        _resolve_password_inputs(args)
    assert args == ["user", "set-password", "alice", "piped"]


def test_no_password_flag_is_noop() -> None:
    args = ["user", "add", "alice", "alice@example.com", "secret"]
    _resolve_password_inputs(args)
    assert args == ["user", "add", "alice", "alice@example.com", "secret"]


def test_unrelated_command_is_noop() -> None:
    args = ["deploy", "myapp", "--password-file", "/tmp/x"]
    _resolve_password_inputs(args)
    # Untouched: only user add / user set-password / auth get-token get the rewrite.
    assert args == ["deploy", "myapp", "--password-file", "/tmp/x"]


def test_auth_get_token_with_password_file(tmp_path: Path) -> None:
    pw_file = tmp_path / "pw.txt"
    pw_file.write_text("s3cret\n", encoding="utf-8")

    args = ["auth", "get-token", "alice", "--password-file", str(pw_file)]
    _resolve_password_inputs(args)

    assert args == ["auth", "get-token", "alice", "s3cret"]


def test_auth_get_token_with_stdin() -> None:
    args = ["auth", "get-token", "alice", "--stdin"]
    fake_stdin = io.StringIO("from-stdin\n")
    with (
        patch.object(sys, "stdin", fake_stdin),
        patch.object(sys.stdin, "isatty", lambda: False, create=True),
    ):
        _resolve_password_inputs(args)
    assert args == ["auth", "get-token", "alice", "from-stdin"]


def test_auth_get_token_no_flag_is_noop() -> None:
    args = ["auth", "get-token", "alice", "literal-password"]
    _resolve_password_inputs(args)
    assert args == ["auth", "get-token", "alice", "literal-password"]


def test_missing_password_file_path_raises() -> None:
    args = ["user", "add", "alice", "alice@example.com", "--password-file"]
    with pytest.raises(ValueError, match="requires a path"):
        _resolve_password_inputs(args)


def test_password_file_unreadable_raises() -> None:
    args = [
        "user",
        "add",
        "alice",
        "alice@example.com",
        "--password-file",
        "/no/such/file",
    ]
    with pytest.raises(ValueError, match="Could not read password file"):
        _resolve_password_inputs(args)


def test_empty_password_file_raises(tmp_path: Path) -> None:
    pw_file = tmp_path / "pw.txt"
    pw_file.write_text("\n", encoding="utf-8")
    args = [
        "user",
        "add",
        "alice",
        "alice@example.com",
        "--password-file",
        str(pw_file),
    ]
    with pytest.raises(ValueError, match="Password is empty"):
        _resolve_password_inputs(args)


def test_stdin_from_tty_refused() -> None:
    args = ["user", "add", "alice", "alice@example.com", "--stdin"]
    with (
        patch.object(sys.stdin, "isatty", lambda: True, create=True),
        pytest.raises(ValueError, match="Refusing to read password"),
    ):
        _resolve_password_inputs(args)


# ---- _resolve_flag_value_sources (§D14 for `hop run --input`) ----


def test_run_input_dash_reads_stdin() -> None:
    args = ["run", "myapp", "flask", "shell", "--input", "-"]
    fake_stdin = io.StringIO("payload\n")
    with (
        patch.object(sys, "stdin", fake_stdin),
        patch.object(sys.stdin, "isatty", lambda: False, create=True),
    ):
        _resolve_flag_value_sources(args)
    assert args[-1] == "payload"


def test_run_input_at_path_reads_file(tmp_path: Path) -> None:
    f = tmp_path / "in.txt"
    f.write_text("from-file\n", encoding="utf-8")
    args = ["run", "myapp", "cat", "--input", f"@{f}"]
    _resolve_flag_value_sources(args)
    assert args[-1] == "from-file"


def test_run_input_literal_unchanged() -> None:
    args = ["run", "myapp", "echo", "--input", "literal"]
    _resolve_flag_value_sources(args)
    assert args[-1] == "literal"


def test_run_input_unrelated_command_noop() -> None:
    args = ["deploy", "myapp", "--input", "-"]
    _resolve_flag_value_sources(args)
    assert args == ["deploy", "myapp", "--input", "-"]


def test_run_input_at_path_missing_file() -> None:
    args = ["run", "myapp", "cat", "--input", "@/nope/missing"]
    with pytest.raises(ValueError, match="Could not read --input file"):
        _resolve_flag_value_sources(args)


def test_run_input_dash_from_tty_refused() -> None:
    args = ["run", "myapp", "cat", "--input", "-"]
    with (
        patch.object(sys.stdin, "isatty", lambda: True, create=True),
        pytest.raises(ValueError, match="Refusing to read --input"),
    ):
        _resolve_flag_value_sources(args)


# ---- _resolve_flag_value_sources (§D14 for `addon email create`) ----


def test_email_password_dash_reads_stdin() -> None:
    args = ["addon", "email", "create", "mail", "--smtp-password", "-"]
    fake_stdin = io.StringIO("re_secret\n")
    with (
        patch.object(sys, "stdin", fake_stdin),
        patch.object(sys.stdin, "isatty", lambda: False, create=True),
    ):
        _resolve_flag_value_sources(args)
    assert args[-1] == "re_secret"


def test_email_password_at_path_reads_file(tmp_path: Path) -> None:
    f = tmp_path / "smtp.secret"
    f.write_text("re_fromfile\n", encoding="utf-8")
    args = ["addon", "email", "create", "mail", "--smtp-password", f"@{f}"]
    _resolve_flag_value_sources(args)
    assert args[-1] == "re_fromfile"


def test_email_password_literal_unchanged() -> None:
    args = ["addon", "email", "create", "mail", "--smtp-password", "re_literal"]
    _resolve_flag_value_sources(args)
    assert args[-1] == "re_literal"


def test_email_password_unrelated_command_noop() -> None:
    args = ["addon", "postgres", "create", "db", "--smtp-password", "-"]
    _resolve_flag_value_sources(args)
    assert args == ["addon", "postgres", "create", "db", "--smtp-password", "-"]


def test_email_password_at_path_missing_file() -> None:
    args = ["addon", "email", "create", "mail", "--smtp-password", "@/nope/missing"]
    with pytest.raises(ValueError, match="Could not read --smtp-password file"):
        _resolve_flag_value_sources(args)


def test_email_password_dash_from_tty_refused() -> None:
    args = ["addon", "email", "create", "mail", "--smtp-password", "-"]
    with (
        patch.object(sys.stdin, "isatty", lambda: True, create=True),
        pytest.raises(ValueError, match="Refusing to read --smtp-password"),
    ):
        _resolve_flag_value_sources(args)


# ---- _resolve_env_set_values (§D14 for `env set KEY=…`) ----


def test_env_set_dash_reads_stdin() -> None:
    args = ["env", "set", "--app", "myapp", "SENTRY_DSN=-"]
    fake_stdin = io.StringIO("https://key@sentry.io/1\n")
    with (
        patch.object(sys, "stdin", fake_stdin),
        patch.object(sys.stdin, "isatty", lambda: False, create=True),
    ):
        _resolve_env_set_values(args)
    assert args[-1] == "SENTRY_DSN=https://key@sentry.io/1"


def test_env_set_at_path_reads_file(tmp_path: Path) -> None:
    f = tmp_path / "dsn.txt"
    f.write_text("https://key@sentry.io/1\n", encoding="utf-8")
    args = ["env", "set", "--app", "myapp", f"SENTRY_DSN=@{f}"]
    _resolve_env_set_values(args)
    assert args[-1] == "SENTRY_DSN=https://key@sentry.io/1"


def test_env_set_literal_unchanged() -> None:
    args = ["env", "set", "--app", "myapp", "DEBUG=true", "PORT=8000"]
    _resolve_env_set_values(args)
    assert args == ["env", "set", "--app", "myapp", "DEBUG=true", "PORT=8000"]


def test_env_set_does_not_treat_the_app_name_as_a_key() -> None:
    """`--app myapp` must not be read as a bare key and trigger a prompt."""
    args = ["env", "set", "--app", "myapp", "DEBUG=true"]
    with patch.object(sys.stdin, "isatty", lambda: True, create=True):
        _resolve_env_set_values(args)
    assert args == ["env", "set", "--app", "myapp", "DEBUG=true"]


def test_env_set_bare_key_prompts_without_echo() -> None:
    args = ["env", "set", "--app", "myapp", "SENTRY_DSN"]
    with (
        patch.object(sys.stdin, "isatty", lambda: True, create=True),
        patch("hop3_cli.commands.arguments.getpass.getpass", return_value="secret"),
    ):
        _resolve_env_set_values(args)
    assert args[-1] == "SENTRY_DSN=secret"


def test_env_set_bare_key_without_tty_is_an_error() -> None:
    """A script must get a loud error, never a hang on an unanswerable prompt."""
    args = ["env", "set", "--app", "myapp", "SENTRY_DSN"]
    with (
        patch.object(sys.stdin, "isatty", lambda: False, create=True),
        pytest.raises(ValueError, match="No value given for SENTRY_DSN"),
    ):
        _resolve_env_set_values(args)


def test_env_set_alias_config_set_is_covered() -> None:
    args = ["config", "set", "--app", "myapp", "TOKEN=@/nope/missing"]
    with pytest.raises(ValueError, match="Could not read value for TOKEN file"):
        _resolve_env_set_values(args)


def test_env_set_unrelated_command_noop() -> None:
    args = ["env", "unset", "--app", "myapp", "SENTRY_DSN"]
    _resolve_env_set_values(args)
    assert args == ["env", "unset", "--app", "myapp", "SENTRY_DSN"]
