# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, NoReturn

from hop3.config import ACME_EMAIL, ACME_WWW, CADDY_ROOT
from hop3.core.artifacts import load_backend_protocol
from hop3.core.identifiers import validate_hostname_list
from hop3.core.protocols import GATE_CHECK_UPSTREAM, GATE_REQUEST_HEADERS, BaseProxy
from hop3.di import create_container
from hop3.lib import (
    Diagnosis,
    abort_with_diagnosis,
    command_output,
    expand_vars,
    log,
)
from hop3.lib.rootd import RootdError, RootdUnavailableError, reload_service
from hop3.platform.certificates import (
    CertificatesManager,
    verify_cert,
    write_private_key,
)
from hop3.plugins.proxy._policy import should_redirect_to_https

from ._templates import (
    CADDY_ACME_CHALLENGE,
    CADDY_BLOCK_GIT,
    CADDY_COMPRESSION,
    CADDY_DENY,
    CADDY_FASTCGI_FRAGMENT,
    CADDY_GATE,
    CADDY_HTTPS_ONLY_TEMPLATE,
    CADDY_PORTMAP_FRAGMENT,
    CADDY_REQUEST_BODY,
    CADDY_SITE_BODY,
    CADDY_TEMPLATE,
    CADDY_TLS_AUTO,
    CADDY_TLS_MANUAL,
    HOP3_INTERNAL_CADDY_CACHE_MAPPING,
    HOP3_INTERNAL_CADDY_STATIC_MAPPING,
)

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.core.env import Env
    from hop3.orm import App


#: `caddy validate` reads one file; anything slower than this is broken.
VALIDATE_TIMEOUT = 5


@dataclass(frozen=True)
class CaddyVirtualHost(BaseProxy):
    backend_protocols: ClassVar[frozenset[str]] = frozenset({"http", "fastcgi"})
    gates_access: ClassVar[bool] = True

    app: App
    env: Env
    workers: dict[str, str]

    def get_proxy_name(self) -> str:
        """Return the proxy name for environment variable construction."""
        return "caddy"

    def __post_init__(self) -> None:
        # SECURITY: validate each host before it lands in the Caddy
        # config. The template interpolates HOST_NAME directly; an
        # un-validated value with a newline or `}` would inject
        # arbitrary Caddy directives. Same shape as the nginx plugin
        # — see notes/security.md §3.5.
        server_name_list = validate_hostname_list(self.env["HOST_NAME"])
        self.env["HOST_NAME"] = " ".join(server_name_list)
        # Caddy site addresses, one per scheme: a bare name is HTTPS-only.
        self.env["HOP3_INTERNAL_CADDY_HTTP_SITES"] = ", ".join(
            f"http://{host}" for host in server_name_list
        )
        self.env["HOP3_INTERNAL_CADDY_HTTPS_SITES"] = ", ".join(
            f"https://{host}" for host in server_name_list
        )

        # Check Caddy version
        caddy_version = command_output("caddy version") or "???"
        log(f"Using Caddy version: {caddy_version}", level=2)

        self.env.update(
            {
                "CADDY_ROOT": str(CADDY_ROOT),
                "ACME_WWW": str(ACME_WWW),
                "CADDY_ACME_EMAIL": ACME_EMAIL,
            },
        )

    def setup_backend(self) -> None:
        """Configure the backend connection (always HTTP for all workers)."""
        # Always use HTTP proxy for all workers (including WSGI)
        # This allows direct HTTP access for development, debugging, and health checks
        bind_address = self.env.get("BIND_ADDRESS", "127.0.0.1")
        port = self.env.get("PORT", "8000")
        self.update_env("CADDY_BACKEND", f"{bind_address}:{port}")
        log(
            f"caddy will proxy app '{self.app_name}' to http://{bind_address}:{port}",
            level=2,
        )

    def setup_certificates(self) -> None:
        """Setup SSL certificates for the application."""
        domain_name = self.env["HOST_NAME"].split()[0]

        # Check if we should use automatic HTTPS or manual certificates
        use_auto_https = self.env.get_bool("CADDY_AUTO_HTTPS", default=False)

        if use_auto_https:
            # Use Caddy's automatic HTTPS with Let's Encrypt
            self.env["HOP3_INTERNAL_CADDY_TLS"] = expand_vars(CADDY_TLS_AUTO, self.env)
            log(
                f"caddy will use automatic HTTPS for '{domain_name}' via Let's Encrypt",
                level=2,
            )
        else:
            # Use manual certificates managed by hop3
            container = create_container()
            try:
                certificate_manager = container.get(CertificatesManager)
                certificate = certificate_manager.get_certificate(domain_name)
                write_private_key(
                    CADDY_ROOT / f"{self.app_name}.key", certificate.get_key()
                )
                (CADDY_ROOT / f"{self.app_name}.crt").write_text(certificate.get_crt())
                # Same post-condition as nginx: never serve an untrusted/expired
                # cert for a public domain under a green deploy (the edrix bug).
                verify_cert(domain_name)
            finally:
                container.close()
            self.env["HOP3_INTERNAL_CADDY_TLS"] = expand_vars(
                CADDY_TLS_MANUAL, self.env
            )
            log(
                f"caddy will use manual certificates for '{domain_name}'",
                level=2,
            )

    def extra_setup(self) -> None:
        """Additional configuration setup."""
        # Conditionally block .git folders from being served
        self.env["HOP3_INTERNAL_CADDY_BLOCK_GIT"] = (
            "" if self.env.get("CADDY_ALLOW_GIT_FOLDERS") else CADDY_BLOCK_GIT
        )
        self.env["CADDY_ACL"] = ""
        self.env["HOP3_INTERNAL_CADDY_ACME"] = expand_vars(
            CADDY_ACME_CHALLENGE, self.env
        )
        self.env["HOP3_INTERNAL_CADDY_GATE"] = (
            expand_vars(
                CADDY_GATE,
                {
                    "APP": self.app_name,
                    "upstream": GATE_CHECK_UPSTREAM,
                    "headers": " ".join(GATE_REQUEST_HEADERS),
                },
            )
            if self.app.access_role is not None
            else ""
        )

        # Largest request body this app accepts. Caddy has no equivalent of
        # nginx's request buffering switch — reverse_proxy streams request
        # bodies unless `request_buffers` is configured — so [proxy]
        # request-buffering needs nothing rendered here: `false` is already
        # what Caddy does.
        self.env["HOP3_INTERNAL_CADDY_REQUEST_BODY"] = expand_vars(
            CADDY_REQUEST_BODY,
            {"max_body_size": self.proxy_settings.max_body_size},
        )
        deny = self.proxy_settings.deny
        self.env["HOP3_INTERNAL_CADDY_DENY"] = (
            expand_vars(CADDY_DENY, {"paths": " ".join(f"{p} {p}/*" for p in deny)})
            if deny
            else ""
        )

        # Enable compression by default
        if not self.env.get_bool("CADDY_DISABLE_COMPRESSION", default=False):
            self.env["HOP3_INTERNAL_CADDY_COMPRESSION"] = CADDY_COMPRESSION
        else:
            self.env["HOP3_INTERNAL_CADDY_COMPRESSION"] = ""

    def generate_config(self) -> None:
        """Generate the Caddyfile configuration."""
        buffer = self.get_proxy_conf()
        self.conf_path.write_text(buffer)
        log(f"Generated Caddy config at {self.conf_path}", level=2)

    @property
    def conf_path(self) -> Path:
        """
        Path to the Caddy configuration file for this app.

        The `.caddyfile` extension is how Caddy recognises the format; the
        platform's Caddyfile imports `*.caddyfile`.
        """
        return CADDY_ROOT / f"{self.app_name}.caddyfile"

    def get_proxy_conf(self) -> str:
        """
        Returns the caddy configuration buffer based on
        specified workers and environment variables.

        Sets up caddy proxy configurations by expanding certain template
        variables using environment settings and adjusts the buffer
        based on conditions like HTTPS-only redirection.
        """
        self.env["HOP3_INTERNAL_CADDY_PORTMAP"] = self._backend_fragment()
        self.env["HOP3_INTERNAL_CADDY_SITE"] = expand_vars(CADDY_SITE_BODY, self.env)

        log(
            f"caddy will serve app '{self.app_name}' on hostname(s)"
            f" '{self.env['HOST_NAME']}'",
            level=2,
        )

        # Choose template based on HTTPS-only setting
        if should_redirect_to_https(self.env, "CADDY_HTTPS_ONLY"):
            buffer = expand_vars(CADDY_HTTPS_ONLY_TEMPLATE, self.env)
            log(
                f"caddy will redirect all HTTP requests to HTTPS for"
                f" '{self.env['HOST_NAME']}'",
                level=2,
            )
        else:
            buffer = expand_vars(CADDY_TEMPLATE, self.env)

        return buffer

    def _backend_fragment(self) -> str:
        """How requests reach the app's port, by what the port speaks."""
        if not any(w in self.workers for w in ("web", "wsgi", "jwsgi", "rwsgi")):
            return ""
        if load_backend_protocol(self.app_path) == "fastcgi":
            return expand_vars(CADDY_FASTCGI_FRAGMENT, self.env)
        return expand_vars(CADDY_PORTMAP_FRAGMENT, self.env)

    def setup_static(self) -> None:
        """
        Configures static path mappings for a Caddy server in the
        environment configuration.
        """
        self.env["HOP3_INTERNAL_CADDY_STATIC_MAPPINGS"] = (
            ""  # Initialize the static mappings string
        )

        static_paths = self.get_static_paths()

        for static_url, static_path_ in static_paths:
            static_path = str(static_path_)
            log(
                f"caddy will serve static files from {static_url} -> {static_path}",
                level=2,
            )
            self.env["HOP3_INTERNAL_CADDY_STATIC_MAPPINGS"] += expand_vars(
                HOP3_INTERNAL_CADDY_STATIC_MAPPING,
                locals(),
            )

        self.env["HOP3_INTERNAL_CADDY_CUSTOM_CLAUSES"] = expand_vars(
            self.include_file("CADDY_INCLUDE_FILE"), self.env
        )

    def check_config(self) -> None:
        """Validate the generated config with ``caddy validate``.

        Unlike nginx, caddy validates the file it is given, so a rejected
        config is judged on its own. A check that cannot *run* is a failure
        all the same: continuing would deploy a config nothing has looked at,
        which is the one thing this method exists to prevent.
        :meth:`BaseProxy.setup` rolls the file back either way.
        """
        try:
            subprocess.run(
                [
                    "caddy",
                    "validate",
                    "--config",
                    str(self.conf_path),
                    "--adapter",
                    "caddyfile",
                ],
                check=True,
                capture_output=True,
                timeout=VALIDATE_TIMEOUT,
            )
        except subprocess.CalledProcessError as e:
            self._abort_validation(
                "`caddy validate` rejected the generated config",
                e.stderr.decode(errors="replace").splitlines(),
            )
        except FileNotFoundError:
            self._abort_validation(
                "the `caddy` binary is not on PATH, so the generated config "
                "could not be checked",
                ["caddy version"],
            )
        except subprocess.TimeoutExpired:
            self._abort_validation(
                f"`caddy validate` did not answer within {VALIDATE_TIMEOUT}s",
                [f"caddy validate --config {self.rejected_conf_path}"],
            )

        log(f"Caddy config validation passed for {self.conf_path}", level=2)

    def _abort_validation(self, reason: str, troubleshooting: list[str]) -> NoReturn:
        abort_with_diagnosis(
            Diagnosis(
                component="Caddy",
                action="validate configuration",
                reason=reason,
                hint=(
                    f"The running caddy config is left untouched; the rejected "
                    f"one is kept at {self.rejected_conf_path} for inspection."
                ),
                troubleshooting=troubleshooting,
            )
        )

    def reload_proxy(self) -> None:
        """
        Reload caddy to apply configuration changes.

        A failed reload is fatal (like nginx): the new routes/cert can't be
        published, so the deploy must not report success.
        """
        # Through hop3-rootd, like nginx. This used to run `sudo -n
        # supervisorctl/systemctl` directly, which fails outright on a host
        # where the hop3 user has no passwordless sudo — and since a failed
        # caddy reload is fatal, *every* caddy deploy aborted on such a box.
        try:
            method = reload_service("caddy")
            log(f"caddy reloaded via {method} (hop3-rootd)", level=2)
        except (RootdError, RootdUnavailableError) as e:
            msg = (
                f"Could not reload caddy: {e}. The new configuration / "
                f"certificate is not live; refusing to report a successful deploy."
            )
            log(f"✗ {msg}", level=1, fg="red")
            raise RuntimeError(msg) from e

    def setup_cache(self) -> None:
        """
        Configure Caddy caching for the application.

        Note: Caddy doesn't have built-in caching like Nginx.
        For production use, you may need to use a Caddy plugin or
        external caching layer. This method sets up basic cache headers.
        """
        self.env["HOP3_INTERNAL_CADDY_CACHE_MAPPINGS"] = ""
        cache_prefixes = self.env.get("CADDY_CACHE_PREFIXES", "")
        if not cache_prefixes:
            return

        prefixes = [p.strip().lstrip("/") for p in cache_prefixes.split(",")]
        prefix_pattern = "|".join(p for p in prefixes if p)
        cache_time_control = self._get_cache_param(
            "CACHE_CONTROL", "cache control", 3600
        )
        log(
            f"caddy will set cache headers for /({prefix_pattern}) prefixes"
            f" with max-age={cache_time_control}",
            level=2,
        )
        self.env["HOP3_INTERNAL_CADDY_CACHE_MAPPINGS"] = expand_vars(
            HOP3_INTERNAL_CADDY_CACHE_MAPPING,
            {
                "cache_prefixes": prefix_pattern,
                "cache_time_control": str(cache_time_control),
                "CADDY_BACKEND": self.env["CADDY_BACKEND"],
            },
        )

    def _get_cache_param(self, key: str, name: str, default: int) -> int:
        """
        Get a cache parameter integer value from the environment.

        Input:
        - key (str): The key to look up in the environment, prefixed with "CADDY_".
        - name (str): The name of the parameter, used for logging in case of an error.
        - default (int): The default integer value to use if retrieval fails.

        Returns:
        - int: The retrieved or default integer value.
        """
        try:
            return self.env.get_int("CADDY_" + key, default)
        except Exception:
            log(f"Invalid {name}, defaulting to {default}", level=2)
            return default
