# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT
from __future__ import annotations

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
