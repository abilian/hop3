# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""
Reload a Hop3-managed system service (``service.reload``), or report
whether one runs (``service.status``).

The privileged half of "apply a config change I just wrote". Three call sites
did this with ``sudo -n systemctl reload <svc>`` from the deployer, which is
the pattern the privilege model rules out: privileged operations belong behind
the daemon, and ``sudo -n`` fails on any host where the ``hop3`` user has no
passwordless sudo. The PostgreSQL one additionally passed ``check=False`` and
threw the result away, so a rewritten ``pg_hba.conf`` that never got applied
looked exactly like one that did — and Docker apps then failed later with an
opaque ``Host 'x' is not allowed``.

Which services may be reloaded is a fixed allow-list here, not a parameter the
caller chooses freely: the service name reaches argv, so an open parameter
would turn one op into "reload anything".
"""

from __future__ import annotations

from typing import Any, Final

from hop3_rootd.exec import CommandTimeoutError, Exec, InvalidBinaryError
from hop3_rootd.ops._base import OpContext, register
from hop3_rootd.protocol import Request

#: Services Hop3 configures and may therefore reload. Adding an entry is a
#: deliberate decision: the name is interpolated into argv.
RELOADABLE_SERVICES: Final[frozenset[str]] = frozenset({
    "caddy",
    "traefik",
    "postgresql",
    "mysql",
    "mariadb",
    "redis",
    "redis-server",
})

_RELOAD_TIMEOUT_SECONDS: Final[float] = 15.0


class ServiceNotAllowedError(Exception):
    """The requested service is not on the reload allow-list."""


class ServiceReloadFailedError(Exception):
    """No available method could reload the service."""


def _reload_methods(exec_: Exec, service: str) -> list[tuple[list[str], str]]:
    """
    Ordered (argv, label) reload attempts for ``service``.

    supervisorctl first: a container image has no systemd, and there
    ``systemctl`` either is absent or answers for a PID 1 that is not running
    the service. On a systemd host supervisorctl is absent instead, so the
    order costs one failed resolve and never a wrong answer.
    """
    methods: list[tuple[list[str], str]] = []
    supervisorctl = exec_.resolve("supervisorctl")
    if supervisorctl is not None:
        methods.append(([supervisorctl, "restart", service], "supervisorctl"))
    systemctl = exec_.resolve("systemctl")
    if systemctl is not None:
        methods.append(([systemctl, "reload", service], "systemctl reload"))
        # Not every unit implements `reload`; `reload-or-restart` is what
        # systemd offers for exactly that case.
        methods.append((
            [systemctl, "reload-or-restart", service],
            "systemctl reload-or-restart",
        ))
    return methods


@register("service.reload")
def reload_service(req: Request, ctx: OpContext) -> dict[str, Any]:
    """
    Reload one allow-listed service, reporting which method worked.

    Args (in ``req.args``):
        service: the service name; must be in :data:`RELOADABLE_SERVICES`.

    Returns:
        ``{"service": ..., "method": "supervisorctl" | "systemctl reload" | ...}``

    Raises:
        ServiceNotAllowedError: the service is not on the allow-list.
        ServiceReloadFailedError: no method succeeded. The caller decides
            whether that is fatal — it is for a proxy publishing new routes,
            and not for one whose file-watch will pick the config up anyway.
    """
    service = req.args.get("service")
    if not isinstance(service, str) or service not in RELOADABLE_SERVICES:
        allowed = ", ".join(sorted(RELOADABLE_SERVICES))
        msg = (
            f"service {service!r} is not reloadable by hop3-rootd (allowed: {allowed})"
        )
        raise ServiceNotAllowedError(msg)

    methods = _reload_methods(ctx.exec, service)
    if not methods:
        msg = (
            f"no reload method available for {service!r}: neither supervisorctl "
            f"nor systemctl is present on the allow-list on this host"
        )
        raise ServiceReloadFailedError(msg)

    last_error: str | None = None
    for argv, label in methods:
        try:
            result = ctx.exec.run(argv, timeout=_RELOAD_TIMEOUT_SECONDS)
        except (InvalidBinaryError, CommandTimeoutError) as e:
            last_error = f"{label}: {e}"
            continue
        if result.success:
            return {"service": service, "method": label}
        last_error = (
            f"{label} returned rc={result.returncode}; stderr={result.stderr.strip()}"
        )

    msg = f"could not reload {service!r}; last error: {last_error}"
    raise ServiceReloadFailedError(msg)


#: Services whose state ``hop3 system status`` reports: the control plane, the
#: app server and whichever proxy the box runs. Read-only, but the name still
#: reaches argv, so it is an allow-list like the one above.
STATUS_SERVICES: Final[frozenset[str]] = frozenset({
    "hop3-server",
    "uwsgi-hop3",
    "nginx",
    "caddy",
    "traefik",
})

_STATUS_TIMEOUT_SECONDS: Final[float] = 10.0


class ServiceStatusUnknownError(Exception):
    """No process manager on this host could say whether the service runs."""


@register("service.status")
def service_status(req: Request, ctx: OpContext) -> dict[str, Any]:
    """
    Whether one allow-listed service is running, as its process manager says.

    Through the daemon because a container's supervisor socket is root's, and
    shelling out to ``systemctl`` there answers for a PID 1 that manages
    nothing. supervisorctl is asked first, for the reason given in
    :func:`_reload_methods`; a service it does not manage falls through to
    systemctl, so a systemd host that also has supervisor installed is still
    answered correctly.

    Args (in ``req.args``):
        service: the service name; must be in :data:`STATUS_SERVICES`.

    Returns:
        ``{"service": ..., "active": bool, "state": <the manager's word>,
        "method": "supervisorctl" | "systemctl"}``

    Raises:
        ServiceNotAllowedError: the service is not on the allow-list.
        ServiceStatusUnknownError: neither manager knows the service.
    """
    service = req.args.get("service")
    if not isinstance(service, str) or service not in STATUS_SERVICES:
        allowed = ", ".join(sorted(STATUS_SERVICES))
        msg = f"service {service!r} has no status in hop3-rootd (allowed: {allowed})"
        raise ServiceNotAllowedError(msg)

    answers: list[str] = []
    supervisorctl = ctx.exec.resolve("supervisorctl")
    if supervisorctl is not None:
        result = ctx.exec.run(
            [supervisorctl, "status", service], timeout=_STATUS_TIMEOUT_SECONDS
        )
        # `<name>  RUNNING  pid 42, uptime …`; rc 3 when stopped, and
        # "no such process" for a program supervisor does not manage.
        fields = result.stdout.split()
        if len(fields) >= 2 and fields[0] == service:
            state = fields[1]
            return {
                "service": service,
                "active": state == "RUNNING",
                "state": state,
                "method": "supervisorctl",
            }
        answers.append(f"supervisorctl: {(result.stdout or result.stderr).strip()}")

    systemctl = ctx.exec.resolve("systemctl")
    if systemctl is not None and _systemd_knows(ctx, systemctl, service, answers):
        result = ctx.exec.run(
            [systemctl, "is-active", service], timeout=_STATUS_TIMEOUT_SECONDS
        )
        # Prints the state (active, inactive, failed, activating…) and exits
        # non-zero for every state but active; "unknown" means no such unit.
        state = result.stdout.strip()
        if state and state != "unknown":
            return {
                "service": service,
                "active": state == "active",
                "state": state,
                "method": "systemctl",
            }
        answers.append(f"systemctl: {(state or result.stderr).strip()}")

    msg = f"no process manager on this host manages {service!r}" + (
        f" ({'; '.join(answers)})" if answers else ""
    )
    raise ServiceStatusUnknownError(msg)


def _systemd_knows(
    ctx: OpContext, systemctl: str, service: str, answers: list[str]
) -> bool:
    """
    Whether systemd has a unit for ``service`` at all.

    `is-active` prints "inactive", not "unknown", for a unit that does not
    exist on current systemd: a proxy that is not installed (caddy on an nginx
    server) read as installed and stopped.
    """
    result = ctx.exec.run(
        [systemctl, "show", "-p", "LoadState", "--value", service],
        timeout=_STATUS_TIMEOUT_SECONDS,
    )
    if result.stdout.strip() == "not-found":
        answers.append(f"systemctl: no unit named {service!r}")
        return False
    return True
