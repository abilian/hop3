# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, EM102, TC001

"""nginx ops: reload, validate_config.

These ops retire the existing /etc/sudoers.d/hop3 fragment that grants
the hop3 user NOPASSWD access to four nginx-related commands. Now that
rootd is the kernel-boundary executor, those calls go through the
typed-intent API and can be audited, validated, and policy-controlled
in one place.

See ADR 041 §2 ("Why nginx is in v1") and §12 ("Sudoers fragment retirement").
"""

from __future__ import annotations

from typing import Any

from hop3_rootd.exec import (
    InvalidBinaryError,
    resolve_allowed_binary,
    run as exec_run,
)
from hop3_rootd.ops._base import OpContext, register
from hop3_rootd.protocol import Request

# --- Errors / constants --------------------------------------------------


class NginxBinaryNotFoundError(Exception):
    """Neither systemctl nor nginx is on the allow-list / on this host."""


# Reload methods, in preferred order. We try them sequentially until one
# succeeds. Mirrors the existing fallback chain in the proxy plugin.
def _reload_methods() -> list[tuple[list[str], str]]:
    """Construct the ordered list of reload commands to try, given the
    binaries actually present on this host. Each entry is (argv, label).
    """
    methods: list[tuple[list[str], str]] = []
    systemctl = resolve_allowed_binary("systemctl")
    if systemctl is not None:
        methods.append(([systemctl, "reload", "nginx"], "systemctl"))
    nginx = resolve_allowed_binary("nginx")
    if nginx is not None:
        methods.append(([nginx, "-s", "reload"], "nginx -s reload"))
    return methods


# --- nginx.reload --------------------------------------------------------


@register("nginx.reload")
def reload_nginx(_req: Request, _ctx: OpContext) -> dict[str, Any]:
    """Reload nginx config without dropping connections.

    Tries systemctl first, then `nginx -s reload`. Reports which method
    succeeded for diagnostics.

    Returns:
        {"method": "systemctl" | "nginx -s reload"}

    Raises NginxBinaryNotFoundError if no working method is available.
    """
    methods = _reload_methods()
    if not methods:
        raise NginxBinaryNotFoundError(
            "no nginx-reload method available "
            "(neither systemctl nor nginx found on the allow-list)"
        )

    last_error: str | None = None
    for argv, label in methods:
        try:
            result = exec_run(argv, timeout=10.0)
        except InvalidBinaryError as e:
            last_error = str(e)
            continue
        if result.success:
            return {"method": label}
        last_error = (
            f"{label} returned rc={result.returncode}; stderr={result.stderr.strip()}"
        )

    # All methods failed.
    raise NginxBinaryNotFoundError(
        f"all nginx-reload methods failed; last error: {last_error}"
    )


# --- nginx.validate_config ------------------------------------------------


@register("nginx.validate_config", audit=False)
def validate_config(_req: Request, _ctx: OpContext) -> dict[str, Any]:
    """Run `nginx -t` to validate the current nginx config files.

    Pure read — doesn't reload anything. nginx -t exits non-zero on
    config errors, so rc != 0 isn't a kernel_error — it's a structured
    {valid: False, errors: [...]} result.
    """
    nginx = resolve_allowed_binary("nginx")
    if nginx is None:
        raise NginxBinaryNotFoundError(
            "nginx not on allow-list (not found on PATH or not whitelisted)"
        )

    try:
        result = exec_run([nginx, "-t"], timeout=10.0)
    except InvalidBinaryError as e:
        raise NginxBinaryNotFoundError(str(e)) from e

    if result.success:
        return {"valid": True}

    # nginx -t writes diagnostics to stderr. Parse out the error lines.
    errors = _parse_nginx_t_errors(result.stderr)
    return {"valid": False, "errors": errors, "raw_stderr": result.stderr}


def _parse_nginx_t_errors(stderr: str) -> list[str]:
    """Pull error / warning lines from nginx -t stderr.

    nginx -t output:
        nginx: [emerg] unexpected "}" in /etc/nginx/...:42
        nginx: configuration file /etc/nginx/nginx.conf test failed

    We return only the meaningful error lines (containing [emerg] /
    [error] / [warn] / similar markers, or the "test failed" verdict).
    """
    if not stderr:
        return []
    out: list[str] = []
    for raw in stderr.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(
            marker in line for marker in ("[emerg]", "[error]", "[warn]", "test failed")
        ):
            out.append(line)
    return out or [stderr.strip()]
