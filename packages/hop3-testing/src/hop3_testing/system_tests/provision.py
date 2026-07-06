# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Provision a fresh cloud server for a `hop3-test run` (ADR 052 Phase 7b.7).

`hop3-test run --provider hetzner` rebuilds a dedicated, operator-supplied box to
a clean OS and hands its IP to the normal remote deploy+test path. This is the
one capability the cloud path had that `run` lacked; everything else (deploy,
test, the shared result store, reporting, app-addon auto-provisioning) `run`
already owns. Reuses the R3 HetznerManager.rebuild_server + wait_for_ssh_ready
(which re-injects the SSH key and updates known_hosts) — the exact calls the
testlab blank-slate makes.
"""

from __future__ import annotations

from rich.console import Console

from hop3_testing.exceptions import ConfigurationError, ServiceStartError

from .config import HetznerConfig
from .hetzner import HetznerManager

SUPPORTED_PROVIDERS = ("hetzner",)


def provision_server(
    *,
    provider: str,
    server_id: int | None = None,
    image: str | None = None,
    verbose: bool = False,
    console: Console | None = None,
) -> str:
    """Rebuild a fresh cloud server and return its IPv4 for a `run` deploy.

    Fail loud on a missing token / server-id / unresolvable SSH key rather than
    silently deploying to a stale box (the blank-slate-requires-config rule).

    Returns:
        The rebuilt server's IPv4 address.
    """
    if provider not in SUPPORTED_PROVIDERS:
        msg = f"Unknown --provider {provider!r}; supported: {', '.join(SUPPORTED_PROVIDERS)}"
        raise ConfigurationError(msg)

    data: dict = {}
    if server_id is not None:
        data["server_id"] = server_id
    if image:
        data["image"] = image
    config = HetznerConfig.from_dict(data)

    if not config.api_token:
        msg = "HETZNER_API_TOKEN is required for --provider hetzner"
        raise ConfigurationError(msg)
    if not config.server_id:
        msg = "--server-id (or HETZNER_SERVER_ID) is required for --provider hetzner"
        raise ConfigurationError(msg)

    console = console or Console()
    manager = HetznerManager(config, verbose=verbose, console=console)

    # Provisioning is a multi-minute OS rebuild + SSH wait; announce each phase
    # unconditionally (not gated on --verbose) so the console never looks hung —
    # a silent `run --provider` reads as a frozen command, not "reinstalling".
    console.print(
        f"\n[bold]Provisioning a fresh {provider} server[/] — rebuilding server "
        f"{config.server_id} to image '{config.image or 'default'}'. "
        "This takes a few minutes (OS reinstall + SSH)…"
    )
    # rebuild_server re-injects the resolved SSH key (raises loud if unresolvable)
    # and resets the host key; wait_for_ssh_ready updates known_hosts.
    info = manager.rebuild_server(image=config.image, timeout=600)
    console.print(f"  OS rebuilt at {info.ipv4}; waiting for SSH…")
    if not manager.wait_for_ssh_ready(timeout=300):
        msg = f"SSH never came up on the rebuilt server {info.ipv4} within 5 minutes"
        raise ServiceStartError(msg)
    console.print(f"  [green]✓[/] Server ready at {info.ipv4}; deploying Hop3…")
    return info.ipv4
