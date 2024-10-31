# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

from hop3.util import expand_vars

TEMPLATES = """
a = 1
b = {a}
c = $APP_NAME
d = ${APP_NAME}
""".strip()


def test_var_expansion():
    env = {"APP_NAME": "test-app"}
    result = expand_vars(TEMPLATES, env)
    assert result == "a = 1\nb = {a}\nc = test-app\nd = test-app"
