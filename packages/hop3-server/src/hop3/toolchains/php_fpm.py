# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The php-fpm pool a PHP application is served by.

Ten catalog applications served through PHP's built-in single-threaded server
or `artisan serve`. Requests serialize, and Nextcloud and Matomo issue
concurrent internal sub-requests, so they deadlock against their own only
worker. This builds the production runtime instead.

php-fpm runs as a uWSGI ``attach-daemon``, not as a service of its own: the
Emperor stays the only process manager on the box (ADR 023), the pool dies
with the app rather than outliving it, and nothing new has to be reconciled
at startup.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from hop3.lib import Diagnosis, abort_with_diagnosis
from hop3.run.fastcgi import FCGI_PING_PATH

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "POOL_CONFIG_NAME",
    "POOL_TEMPLATE_NAME",
    "document_root",
    "php_fpm_binary",
    "pool_config",
    "web_command",
]

#: Written at build time, with the port left as a placeholder.
POOL_TEMPLATE_NAME = "php-fpm.conf.in"

#: Written at start, once the port is known.
POOL_CONFIG_NAME = "php-fpm.conf"

#: The port is allocated at deploy, so it cannot be baked in at build.
_PORT_PLACEHOLDER = "__HOP3_PORT__"

#: Frameworks that put their front controller in a subdirectory. Serving the
#: project root instead exposes `.env`, `composer.json` and the whole vendor
#: tree over HTTP, so this is a security default, not a convenience.
_FRONT_CONTROLLER_DIRS = ("public", "web", "htdocs")

#: php-fpm binaries are versioned on Debian (`php-fpm8.3`), with the unversioned
#: name sometimes absent even though the package is installed.
_BINARY_CANDIDATES = (
    "php-fpm8.4",
    "php-fpm8.3",
    "php-fpm8.2",
    "php-fpm8.1",
    "php-fpm",
)


def php_fpm_binary() -> str:
    """
    The php-fpm executable to run, or abort saying what is missing.

    A PHP app with no php-fpm cannot be served, and the failure has to land
    here rather than as a crash-looping vassal five minutes later.
    """
    found = next((p for c in _BINARY_CANDIDATES if (p := shutil.which(c))), None)
    if not found:
        abort_with_diagnosis(
            Diagnosis(
                component="PHP toolchain",
                action="locate php-fpm",
                reason=(
                    "no php-fpm binary is on PATH, so the application cannot "
                    f"be served (looked for: {', '.join(_BINARY_CANDIDATES)})"
                ),
                hint=(
                    "Install it on the server — the Hop3 installer does this "
                    "as part of the PHP toolchain — then redeploy."
                ),
                troubleshooting=["apt-get install php-fpm", "php-fpm -v"],
            )
        )
    return found


def document_root(src_path: Path, declared: str = "") -> Path:
    """
    Where nginx should serve from, which is not always the project root.

    Laravel and Symfony keep their front controller under `public/`; serving
    the root would publish the application's own source and `.env`. A recipe
    that knows better says so with `PHP_DOCUMENT_ROOT`.
    """
    if declared:
        root = (src_path / declared).resolve()
        if not root.is_dir():
            abort_with_diagnosis(
                Diagnosis(
                    component="PHP toolchain",
                    action="resolve document root",
                    reason=(
                        f"PHP_DOCUMENT_ROOT is {declared!r}, which is not a "
                        f"directory in the application source"
                    ),
                    hint="Set it to a path relative to the project root, or unset it.",
                )
            )
        return root
    for name in _FRONT_CONTROLLER_DIRS:
        candidate = src_path / name
        if (candidate / "index.php").is_file():
            return candidate
    return src_path


def pool_config(app_name: str, log_path: Path) -> str:
    """
    The pool, with the listen port left as a placeholder.

    ``ping.path`` is what the readiness gate asks for: php-fpm answers it from
    a pool child, so a master that has forked no working child stays silent
    and the deploy correctly fails. ``catch_workers_output`` is what makes a
    PHP fatal reach the app's log instead of being dropped.
    """
    return f"""\
[global]
error_log = {log_path}
daemonize = no

[{app_name}]
listen = 127.0.0.1:{_PORT_PLACEHOLDER}
pm = dynamic
pm.max_children = 10
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 4
pm.max_requests = 500
ping.path = {FCGI_PING_PATH}
ping.response = pong
catch_workers_output = yes
decorate_workers_output = no
"""


def web_command(binary: str, app_path: Path) -> str:
    """
    The ``attach-daemon`` line that runs the pool.

    The port is substituted at start because that is when it exists. uWSGI
    already runs this through ``sh -c`` and already expands ``$PORT`` there,
    so the substitution costs one `sed` rather than a deploy-time hook that
    a recipe's own `before-run` could override.

    ponytail: a sed at start is the cheap way to get a deploy-time value into
    a build-time file. The upgrade path is a process manager that renders its
    children's configs itself (ADR 023), at which point this line goes away.
    """
    template = app_path / POOL_TEMPLATE_NAME
    config = app_path / POOL_CONFIG_NAME
    return (
        f"sed 's/{_PORT_PLACEHOLDER}/'\"$PORT\"'/' {template} > {config} "
        f"&& exec {binary} --nodaemonize --fpm-config {config}"
    )
