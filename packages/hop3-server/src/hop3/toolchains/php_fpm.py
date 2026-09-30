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

from hop3.lib import Diagnosis, abort_with_diagnosis, log
from hop3.run.fastcgi import FCGI_PING_PATH

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "POOL_CONFIG_NAME",
    "POOL_TEMPLATE_NAME",
    "document_root",
    "php_fpm_binary",
    "pool_config",
    "render_pool_config",
    "serve_with_php_fpm",
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
_FRONT_CONTROLLER_DIRS = ("public", "web", "htdocs", "www")

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
    that knows better says so with ``[build].document-root``.

    That used to read ``PHP_DOCUMENT_ROOT`` out of the toolchain's env, which
    is parsed from ``<app_path>/ENV`` — a file nothing in Hop3 writes. So the
    knob was documented, validated, and unreachable: a recipe that set it got
    silent auto-detection, and for an app whose web root is not one of the
    names below that means serving the project root, data directory included.
    """
    if declared:
        root = (src_path / declared).resolve()
        if not root.is_dir():
            abort_with_diagnosis(
                Diagnosis(
                    component="PHP toolchain",
                    action="resolve document root",
                    reason=(
                        f"[build].document-root is {declared!r}, which is not "
                        f"a directory in the application source"
                    ),
                    hint=(
                        "Set it to a path relative to the project root, or "
                        "remove it and let the front controller be detected."
                    ),
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

    ``clear_env = no`` is what makes the app's environment reach it at all.
    php-fpm clears a worker's environment by default, and Hop3's entire addon
    model is environment injection: `DATABASE_URL`, `MYSQL_*`, `REDIS_URL` and
    every `[env]` value are exported by the `attach-daemon` line that starts
    this pool, and without this they stop at the master. Every other runtime
    Hop3 supervises — gunicorn, node, the old `php -S` — inherits them, so
    leaving the default here would mean a PHP app alone could not read the
    credentials the platform provisioned for it.
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
clear_env = no
"""


def serve_with_php_fpm(
    app_name: str, app_path: Path, binary: str, root: Path
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Write the pool template; return the runtime's env vars and workers.

    One contract for every build path that serves PHP through php-fpm: the
    PHP toolchain with the system's php-fpm, the Nix builder with the one in
    the store. The spawn path renders the template once the port exists, and
    the proxy serves ``root`` for everything that is not a script.
    """
    log_path = app_path / "log" / "php-fpm.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    template = app_path / POOL_TEMPLATE_NAME
    template.write_text(pool_config(app_name, log_path))
    log(f"php-fpm pool written to {template}", level=2, fg="cyan")
    log(f"php-fpm document root: {root}", level=2, fg="cyan")
    return (
        {"PHP_DOCUMENT_ROOT": str(root)},
        {"web": web_command(binary, app_path)},
    )


def render_pool_config(template: str, port: str) -> str:
    """
    The pool config for a port that only exists once the app is started.

    Called from the spawn path, where the port has just been resolved. It was
    once a ``sed`` at the head of the worker's command line, which could not
    work: uWSGI's ``attach-daemon`` wrapper prepends ``exec`` to the command,
    so the shell was replaced by ``sed`` and the ``&& exec php-fpm`` after it
    was never reached. The pool never started, and no test saw it, because the
    tests asserted the shape of that command string rather than that a pool
    came up — and because every PHP recipe still declares ``[run].start``,
    which overrides this worker, so no deployed app had yet taken the path.
    """
    return template.replace(_PORT_PLACEHOLDER, port)


def web_command(binary: str, app_path: Path) -> str:
    """
    The ``attach-daemon`` line that runs the pool.

    One program and no shell operators. The caller wraps this in
    ``sh -c "… ; exec <command>"``, so anything compound here would put
    ``exec`` on the wrong word — which is exactly what happened while the
    port substitution lived on this line. The config it names is written by
    :func:`render_pool_config` before the worker is created.
    """
    return f"{binary} --nodaemonize --fpm-config {app_path / POOL_CONFIG_NAME}"
