# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
PHP's built-in server must not run single-threaded.

Regression: Nextcloud served 504s after 60 seconds. `php -S` handles one
request at a time, and Nextcloud's richdocuments app fetches the app's OWN
public URL — so the single worker sat waiting for a reply only it could
produce. Same app, same database, with workers: 200 in 0.12s.

`php artisan serve` is the same server, so it deadlocks identically. Ten of the
twenty catalog apps run on one or the other, which is why this lives in the
platform rather than in each recipe.
"""

from __future__ import annotations

import pytest

from hop3.run.spawn import (
    PHP_BUILTIN_SERVER_WORKERS,
    _ensure_php_server_concurrency,
)


@pytest.mark.parametrize(
    "command",
    [
        "php -S 0.0.0.0:$PORT",
        "php -S 0.0.0.0:${PORT:-8080} -t htdocs",
        "php artisan serve --host=0.0.0.0 --port=$PORT",
    ],
)
def test_builtin_server_gets_workers(command) -> None:
    env: dict[str, str] = {}

    _ensure_php_server_concurrency(env, {"web": command}, "app")

    assert env["PHP_CLI_SERVER_WORKERS"] == PHP_BUILTIN_SERVER_WORKERS


@pytest.mark.parametrize(
    "command",
    ["gunicorn app:application", "node server/server.js", "./forgejo web"],
)
def test_other_servers_are_left_alone(command) -> None:
    """Only PHP's built-in server has this defect; nothing else is touched."""
    env: dict[str, str] = {}

    _ensure_php_server_concurrency(env, {"web": command}, "app")

    assert "PHP_CLI_SERVER_WORKERS" not in env


def test_an_explicit_value_wins() -> None:
    """The platform supplies a default, it does not override the operator."""
    env = {"PHP_CLI_SERVER_WORKERS": "16"}

    _ensure_php_server_concurrency(env, {"web": "php -S 0.0.0.0:$PORT"}, "app")

    assert env["PHP_CLI_SERVER_WORKERS"] == "16"


def test_a_non_web_worker_still_counts() -> None:
    """The built-in server can be declared under any worker name."""
    env: dict[str, str] = {}

    _ensure_php_server_concurrency(env, {"api": "php -S 0.0.0.0:$PORT"}, "app")

    assert env["PHP_CLI_SERVER_WORKERS"] == PHP_BUILTIN_SERVER_WORKERS
