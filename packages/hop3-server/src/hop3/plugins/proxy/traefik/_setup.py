# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import yaml

from hop3.config import TRAEFIK_ROOT
from hop3.core.identifiers import validate_hostname_list
from hop3.core.protocols import GATE_CHECK_UPSTREAM, GATE_REQUEST_HEADERS, BaseProxy
from hop3.di import create_container
from hop3.lib import (
    Diagnosis,
    abort_with_diagnosis,
    command_output,
    log,
)
from hop3.lib.rootd import RootdError, RootdUnavailableError, reload_service
from hop3.platform.certificates import (
    CertificatesManager,
    verify_cert,
    write_private_key,
)
from hop3.plugins.proxy._policy import should_redirect_to_https

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.core.env import Env
    from hop3.orm import App


_SIZE_UNITS = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}

#: No client comes from the broadcast address, so an allow-list naming only it
#: refuses everyone with a 403: Traefik has no plain "respond 403".
_NOBODY = ["255.255.255.255/32"]


def parse_size_to_bytes(size: str) -> int:
    """
    Turn a `[proxy] max-body-size` value into bytes for Traefik.

    The schema has already constrained the shape to digits plus an optional
    K/M/G, so anything else here is a platform bug, not user input.
    """
    unit = size[-1].upper() if size and size[-1].isalpha() else ""
    number = size[:-1] if unit else size
    return int(number) * _SIZE_UNITS[unit]


@dataclass(frozen=True)
class TraefikVirtualHost(BaseProxy):
    """
    One app's routes, as a Traefik dynamic-configuration file.

    Traefik reads every file in ``TRAEFIK_ROOT`` through its file provider.
    The config is built as data and dumped as YAML, so no hostname or value
    can change its structure. Traefik proxies and serves no files: the ACME
    webroot and static paths are beyond it, and ``BaseProxy`` refuses them.
    """

    serves_files: ClassVar[bool] = False
    gates_access: ClassVar[bool] = True
    refuses_paths: ClassVar[bool] = False

    app: App
    env: Env
    workers: dict[str, str]

    def get_proxy_name(self) -> str:
        """Return the proxy name for environment variable construction."""
        return "traefik"

    def __post_init__(self) -> None:
        # SECURITY: validate every host before it reaches a router rule, where
        # a backtick would end the Host() matcher. See notes/security.md §3.5.
        hosts = validate_hostname_list(self.env["HOST_NAME"])
        self.env["HOST_NAME"] = " ".join(hosts)

        traefik_version = command_output("traefik version") or "???"
        log(f"Using Traefik version: {traefik_version}", level=2)

    @property
    def hosts(self) -> list[str]:
        return self.env["HOST_NAME"].split()

    @property
    def conf_path(self) -> Path:
        """Path to the Traefik configuration file for this app."""
        return TRAEFIK_ROOT / f"{self.app_name}.yml"

    def setup_backend(self) -> None:
        """Point the service at the app's HTTP port."""
        bind_address = self.env.get("BIND_ADDRESS", "127.0.0.1")
        port = self.env.get("PORT", "8000")
        self.update_env("TRAEFIK_BACKEND", f"http://{bind_address}:{port}")
        log(
            f"traefik will proxy app '{self.app_name}' to http://{bind_address}:{port}",
            level=2,
        )

    def setup_certificates(self) -> None:
        """Install the app's certificate, issued by Hop3's certificate engine."""
        domain_name = self.hosts[0]
        container = create_container()
        try:
            certificate = container.get(CertificatesManager).get_certificate(
                domain_name
            )
            write_private_key(self._key_path, certificate.get_key())
            self._crt_path.write_text(certificate.get_crt())
            # Same post-condition as nginx: never serve an untrusted/expired
            # cert for a public domain under a green deploy (the edrix bug).
            verify_cert(domain_name)
        finally:
            container.close()

    @property
    def _crt_path(self) -> Path:
        return TRAEFIK_ROOT / f"{self.app_name}.crt"

    @property
    def _key_path(self) -> Path:
        return TRAEFIK_ROOT / f"{self.app_name}.key"

    def setup_cache(self) -> None:
        """Cache headers are a middleware; see :meth:`_middlewares`."""

    def setup_static(self) -> None:
        """Nothing to do: an app with static paths was refused before setup."""

    def extra_setup(self) -> None:
        if not self.proxy_settings.request_buffering:
            log(
                f"traefik cannot stream request bodies and enforce a size limit at "
                f"the same time; '{self.app_name}' gets the limit "
                f"({self.proxy_settings.max_body_size}) and buffering.",
                level=4,
                fg="yellow",
            )

    def generate_config(self) -> None:
        """Write this app's Traefik dynamic configuration."""
        self.conf_path.write_text(self.get_proxy_conf())
        log(f"Generated Traefik config at {self.conf_path}", level=2)

    def get_proxy_conf(self) -> str:
        """The app's dynamic configuration, as YAML."""
        return yaml.safe_dump(self.dynamic_config(), sort_keys=False)

    def dynamic_config(self) -> dict[str, Any]:
        """
        Routers, service, middlewares and certificate for this app.

        Each scheme gets a router of its own: a router with ``tls`` matches
        only HTTPS requests, so one router on both entry points left plain
        HTTP unrouted.
        """
        app = self.app_name
        rule = " || ".join(f"Host(`{host}`)" for host in self.hosts)
        middlewares = self._middlewares()
        chain = list(middlewares)
        service = f"{app}-service"

        https: dict[str, Any] = {
            "rule": rule,
            "entryPoints": ["websecure"],
            "service": service,
            "tls": {},
            "middlewares": chain,
        }
        http: dict[str, Any] = {
            "rule": rule,
            "entryPoints": ["web"],
            "service": service,
        }
        if should_redirect_to_https(self.env, "TRAEFIK_HTTPS_ONLY"):
            middlewares[f"{app}-https-redirect"] = {
                "redirectScheme": {"scheme": "https", "permanent": True}
            }
            http["middlewares"] = [f"{app}-https-redirect"]
        else:
            http["middlewares"] = chain
        routers: dict[str, Any] = {f"{app}-http": http, f"{app}-https": https}
        services: dict[str, Any] = {
            service: {
                "loadBalancer": {"servers": [{"url": self.env["TRAEFIK_BACKEND"]}]}
            }
        }

        if not self.env.get("TRAEFIK_ALLOW_GIT_FOLDERS"):
            # A longer rule outranks the app's router: Traefik's default
            # priority is the rule's length.
            middlewares[f"{app}-deny"] = {"ipAllowList": {"sourceRange": _NOBODY}}
            for name, router in list(routers.items()):
                routers[f"{name}-git"] = {
                    **router,
                    "rule": f"({rule}) && PathPrefix(`/.git`)",
                    "middlewares": [f"{app}-deny"],
                }

        if self.app.access_role is not None:
            self._add_gate(rule, routers, services, middlewares)

        return {
            "http": {
                "routers": routers,
                "services": services,
                "middlewares": middlewares,
            },
            "tls": {
                "certificates": [
                    {"certFile": str(self._crt_path), "keyFile": str(self._key_path)}
                ]
            },
        }

    def _add_gate(
        self,
        rule: str,
        routers: dict[str, Any],
        services: dict[str, Any],
        middlewares: dict[str, Any],
    ) -> None:
        """
        The access gate (ADR 062): every HTTPS request is checked first.

        ``forwardAuth`` deletes each listed request header, then sets those
        the check returned; a non-2xx answer (the sign-in redirect, a 403)
        goes to the client as is. ``/_hop3/auth/`` goes to hop3-server, on
        the app's host, so the sign-in can set the gate cookie there.
        """
        app = self.app_name
        middlewares[f"{app}-gate-app"] = {
            "headers": {"customRequestHeaders": {"X-Hop3-App": app}}
        }
        middlewares[f"{app}-gate"] = {
            "forwardAuth": {
                "address": f"http://{GATE_CHECK_UPSTREAM}/auth/check?redirect=1",
                "authResponseHeaders": list(GATE_REQUEST_HEADERS),
                # Traefik sets the X-Forwarded-* the check reads; none from
                # the client. The check's answers are a few hundred bytes.
                "trustForwardHeader": False,
                "maxResponseBodySize": 65536,
            }
        }
        https = routers[f"{app}-https"]
        https["middlewares"] = [f"{app}-gate-app", f"{app}-gate", *https["middlewares"]]
        routers[f"{app}-https-hop3"] = {
            "rule": f"({rule}) && PathPrefix(`/_hop3/auth/`)",
            "entryPoints": ["websecure"],
            "service": f"{app}-hop3",
            "tls": {},
            "middlewares": [f"{app}-gate-app"],
        }
        services[f"{app}-hop3"] = {
            "loadBalancer": {"servers": [{"url": f"http://{GATE_CHECK_UPSTREAM}"}]}
        }

    def _middlewares(self) -> dict[str, Any]:
        """The middlewares every request to the app passes through, in order."""
        app = self.app_name
        max_body = parse_size_to_bytes(self.proxy_settings.max_body_size)
        middlewares: dict[str, Any] = {
            f"{app}-compression": {"compress": {}},
            # Traefik enforces a body limit only through buffering, so the
            # limit and the buffering are one decision here, unlike nginx.
            f"{app}-body-limit": {"buffering": {"maxRequestBodyBytes": max_body}},
        }
        cache_time_control = self.env.get_int("TRAEFIK_CACHE_CONTROL", 0)
        if cache_time_control > 0:
            middlewares[f"{app}-cache-headers"] = {
                "headers": {
                    "customResponseHeaders": {
                        "Cache-Control": f"public, max-age={cache_time_control}"
                    }
                }
            }
        return middlewares

    def check_config(self) -> None:
        """Check that the generated config parses as YAML.

        Traefik has no validate command for a single dynamic-config file, so
        this is a syntax check and not a semantic one. It still has to fail
        the deploy: traefik file-watches this directory and skips a file it
        cannot parse, so the app would simply never be routed and nothing
        would say why. :meth:`BaseProxy.setup` rolls the file back.
        """
        try:
            yaml.safe_load(self.conf_path.read_text())
        except yaml.YAMLError as e:
            abort_with_diagnosis(
                Diagnosis(
                    component="Traefik",
                    action="validate configuration",
                    reason=f"the generated config is not valid YAML: {e}",
                    hint=(
                        f"Traefik keeps serving what it already loaded; the "
                        f"rejected config is kept at {self.rejected_conf_path} "
                        f"for inspection."
                    ),
                    troubleshooting=[f"cat {self.rejected_conf_path}"],
                )
            )

        log(f"Traefik config validation passed for {self.conf_path}", level=2)

    def reload_proxy(self) -> None:
        """
        Reload traefik to apply configuration changes.

        Unlike nginx/caddy, traefik commonly file-watches its dynamic config and
        reloads itself, so a failed *explicit* reload is often benign — hence it
        is surfaced LOUDLY (not silently) rather than raised, to avoid failing
        legitimate file-watch deploys. (A stricter contract would detect whether
        the file provider is configured before deciding.)
        """
        # Through hop3-rootd, like nginx and caddy — `sudo -n` fails on a host
        # without passwordless sudo for the hop3 user. Unlike caddy this stays
        # non-fatal: traefik's file provider watches its config directory, so
        # the change lands without an explicit reload. The warning is what
        # keeps that from being a silent assumption.
        try:
            method = reload_service("traefik")
            log(f"traefik reloaded via {method} (hop3-rootd)", level=2)
        except (RootdError, RootdUnavailableError) as e:
            log(
                f"⚠ Could not explicitly reload traefik ({e}); relying on "
                "its file-watch to apply the new config — verify the app is served.",
                level=1,
                fg="yellow",
            )
