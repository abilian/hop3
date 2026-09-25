# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""An unknown command is named in full, so the suggestion is drawn against it."""

from __future__ import annotations

from hop3.lib.suggestions import closest_matches
from hop3.server.controllers.rpc import (
    _unknown_command_error,
    commands,
    format_command_name,
    typed_command_name,
)


def test_typed_name_keeps_the_token_that_broke_the_walk() -> None:
    # `admin` is a registered namespace, `admin set-password` is not.
    assert typed_command_name(["admin", "set-password"]) == ("admin", "set-password")


def test_typed_name_stops_at_the_first_unknown_token() -> None:
    # Everything after the break is an argument, not part of the name.
    assert typed_command_name(["admin", "set-password", "admin", "s3cret"]) == (
        "admin",
        "set-password",
    )


def test_typed_name_of_an_unknown_first_token_is_that_token() -> None:
    assert typed_command_name(["zzzz", "yyyy"]) == ("zzzz",)


def test_suggestion_points_at_the_real_command() -> None:
    typed = format_command_name(typed_command_name(["admin", "set-password"]))
    error = _unknown_command_error("...", typed)
    assert "user set-password" in error.data["candidates"]


def test_registry_still_matches_a_real_command() -> None:
    known = [format_command_name(name) for name in commands]
    assert "user set-password" in known
    # `user set-role` is close too; the real command must still rank first.
    assert closest_matches("user set-passwrd", known)[0] == "user set-password"
