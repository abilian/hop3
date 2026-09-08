# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Env values survive the two layers of quoting in the ``attach-daemon`` line.

Every exported value is wrapped in ``'...'`` and that whole string is then
embedded in the double-quoted argument of ``sh -c "…"``. Inside double quotes a
shell still interprets ``$``, a backtick, a backslash and a double quote, so
single-quoting alone does not protect the value. It did not: a JSON-valued
setting arrived with its quotes stripped (paperless-ngx's
PAPERLESS_PROXY_SSL_HEADER reached Django as ``[HTTP_X_FORWARDED_PROTO,https]``
and crashed every worker), and a generated password containing ``$`` would have
been silently mangled into a credential that no longer opened the account.

These run the value through a real ``/bin/sh`` the same way uWSGI does, and
assert it comes back byte-identical.
"""

from __future__ import annotations

import subprocess

import pytest

from hop3.run.uwsgi.worker import _quote_env_value

ROUND_TRIP_CASES = [
    pytest.param("plain-value-123", id="plain"),
    pytest.param('["HTTP_X_FORWARDED_PROTO","https"]', id="json-list"),
    pytest.param("it's a password", id="apostrophe"),
    pytest.param('a$b"c`d\\e', id="every-metacharacter"),
    pytest.param("postgresql://u:p$w`x'y@h:5432/db", id="database-url"),
    pytest.param("$PORT", id="literal-dollar-name"),
]


def _export_and_read_back(value: str) -> str:
    """Emit the export the way ``attach_daemon`` does, and read the value back."""
    line = (
        f"""sh -c "cd /tmp && export V='{_quote_env_value(value)}'; exec printenv V" """
    )
    result = subprocess.run(
        ["/bin/sh", "-c", line],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.rstrip("\n")


@pytest.mark.parametrize("value", ROUND_TRIP_CASES)
def test_env_value_survives_both_quoting_layers(value: str) -> None:
    assert _export_and_read_back(value) == value


def test_unescaped_value_is_what_regressed() -> None:
    """The old single-quote-only escaping loses the JSON quotes — pin the bug."""
    naive = '["HTTP_X_FORWARDED_PROTO","https"]'.replace("'", "'\\''")
    line = f"""sh -c "cd /tmp && export V='{naive}'; exec printenv V" """
    result = subprocess.run(
        ["/bin/sh", "-c", line], capture_output=True, text=True, check=True
    )
    assert result.stdout.rstrip("\n") == "[HTTP_X_FORWARDED_PROTO,https]"
