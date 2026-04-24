# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from hop3.lib import expand_vars

TEMPLATES = """
a = 1
b = {a}
c = $APP_NAME
d = ${APP_NAME}
""".strip()


def test_var_expansion() -> None:
    env = {"APP_NAME": "test-app"}
    result = expand_vars(TEMPLATES, env)
    assert result == "a = 1\nb = {a}\nc = test-app\nd = test-app"


def test_expand_vars_rejects_nul_byte_in_value() -> None:
    """NUL bytes have no legitimate use in any config we render; treat them
    as a reliable injection signature even though HOST_NAME-style attacks
    are primarily caught by RPC-boundary validation."""
    env = {"HOST_NAME": "example.com\x00evil"}
    with pytest.raises(ValueError, match="NUL byte"):
        expand_vars("server_name $HOST_NAME;", env)


def test_expand_vars_accepts_multiline_value() -> None:
    """Multi-line values are legitimate: the codebase composes nginx
    fragments by substituting pre-rendered blocks as values."""
    env = {"BLOCK": "line1\nline2\nline3"}
    result = expand_vars("prefix\n$BLOCK\nsuffix", env)
    assert result == "prefix\nline1\nline2\nline3\nsuffix"
