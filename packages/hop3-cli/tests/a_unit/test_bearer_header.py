# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A malformed API token is refused without being printed.

A token holding a line break (two tokens read from one file) made the HTTP
library reject the `Authorization` header with an error that quoted it, and
the CLI printed that error: the bearer token ended up in a test run's output.
"""

from __future__ import annotations

import pytest
from hop3_cli.exceptions import CliError
from hop3_cli.tokens import bearer_header

_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhIn0.c2lnbmF0dXJl"


def test_a_token_becomes_its_header():
    assert bearer_header(_TOKEN) == f"Bearer {_TOKEN}"


@pytest.mark.parametrize("bad", [f"{_TOKEN}\n{_TOKEN}", f" {_TOKEN}", f"{_TOKEN}\t"])
def test_a_malformed_token_is_refused_without_being_shown(bad):
    with pytest.raises(CliError) as raised:
        bearer_header(bad)
    assert _TOKEN not in str(raised.value)
