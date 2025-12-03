# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.config import ACME_EMAIL, ACME_WWW, CADDY_ROOT
from hop3.core.protocols import BaseProxy
from hop3.di import create_container
from hop3.lib import command_output, expand_vars, log
from hop3.platform.certificates import CertificatesManager

from ._templates import (
    CADDY_BLOCK_GIT,
    CADDY_COMPRESSION,
    CADDY_HTTPS_ONLY_TEMPLATE,
    CADDY_PORTMAP_FRAGMENT,
    CADDY_TEMPLATE,
    CADDY_TLS_AUTO,
    CADDY_TLS_MANUAL,
    HOP3_INTERNAL_CADDY_CACHE_MAPPING,
    HOP3_INTERNAL_CADDY_STATIC_MAPPING,
)

if TYPE_CHECKING:
    from hop3.core.env import Env
    from hop3.orm import App


@dataclass(frozen=True)
class CaddyVirtualHost(BaseProxy):
    app: App
    env: Env
    workers: dict[str, str]

    def get_proxy_name(self) -> str:
        """Return the proxy name for environment variable construction."""
        return "caddy"

    def __post_init__(self) -> None:
        # Normalize server name list
        server_name_list = self.env["HOST_NAME"].split(",")
        # Caddy uses space-separated alternative names in the server block
        self.env["HOST_NAME"] = " ".join(server_name_list)

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

    def setup_backend(self):
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
                (CADDY_ROOT / f"{self.app_name}.key").write_text(certificate.get_key())
                (CADDY_ROOT / f"{self.app_name}.crt").write_text(certificate.get_crt())
            finally:
                container.close()
            self.env["HOP3_INTERNAL_CADDY_TLS"] = expand_vars(
                CADDY_TLS_MANUAL, self.env
            )
            log(
                f"caddy will use manual certificates for '{domain_name}'",
                level=2,
            )

    def extra_setup(self):
        """Additional configuration setup."""
        # Conditionally block .git folders from being served
        self.env["HOP3_INTERNAL_CADDY_BLOCK_GIT"] = (
            "" if self.env.get("CADDY_ALLOW_GIT_FOLDERS") else CADDY_BLOCK_GIT
        )
        self.env["CADDY_ACL"] = ""

        # Enable compression by default
        if not self.env.get_bool("CADDY_DISABLE_COMPRESSION", default=False):
            self.env["HOP3_INTERNAL_CADDY_COMPRESSION"] = CADDY_COMPRESSION
        else:
            self.env["HOP3_INTERNAL_CADDY_COMPRESSION"] = ""

    def generate_config(self) -> None:
        """Generate the Caddyfile configuration."""
        buffer = self.get_proxy_conf()
        self.caddy_conf_path.write_text(buffer)
        log(f"Generated Caddy config at {self.caddy_conf_path}", level=2)

    @property
    def caddy_conf_path(self) -> Path:
        """Path to the Caddy configuration file for this app."""
        return CADDY_ROOT / f"{self.app_name}.caddy"

    def get_proxy_conf(self) -> str:
        """Returns the caddy configuration buffer based on
        specified workers and environment variables.

        Sets up caddy proxy configurations by expanding certain template
        variables using environment settings and adjusts the buffer
        based on conditions like HTTPS-only redirection.
        """
        # Setup reverse proxy if we have web workers
        if (
            "web" in self.workers
            or "wsgi" in self.workers
            or "jwsgi" in self.workers
            or "rwsgi" in self.workers
        ):
            self.env["HOP3_INTERNAL_CADDY_PORTMAP"] = expand_vars(
                CADDY_PORTMAP_FRAGMENT, self.env
            )
        else:
            self.env["HOP3_INTERNAL_CADDY_PORTMAP"] = ""

        log(
            f"caddy will serve app '{self.app_name}' on hostname(s)"
            f" '{self.env['HOST_NAME']}'",
            level=2,
        )

        # Choose template based on HTTPS-only setting
        if self.env.get_bool("CADDY_HTTPS_ONLY"):
            buffer = expand_vars(CADDY_HTTPS_ONLY_TEMPLATE, self.env)
            log(
                f"caddy will redirect all HTTP requests to HTTPS for"
                f" '{self.env['HOST_NAME']}'",
                level=2,
            )
        else:
            buffer = expand_vars(CADDY_TEMPLATE, self.env)

        return buffer

    def setup_static(self) -> None:
        """Configures static path mappings for a Caddy server in the
        environment configuration."""
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

        # Include custom Caddy configuration if specified
        if caddy_include_file := self.env.get("CADDY_INCLUDE_FILE"):
            tpl = Path(self.app_path, caddy_include_file).read_text()
        else:
            tpl = ""
        self.env["HOP3_INTERNAL_CADDY_CUSTOM_CLAUSES"] = expand_vars(tpl, self.env)

    def check_config(self) -> None:
        """Validate the Caddy configuration file."""
        try:
            # Caddy can validate a specific config file
            subprocess.run(
                ["caddy", "validate", "--config", str(self.caddy_conf_path)],
                check=True,
                capture_output=True,
                timeout=5,
            )
            log(f"Caddy config validation passed for {self.caddy_conf_path}", level=2)
        except subprocess.CalledProcessError as e:
            log(
                f"Error: broken caddy config - {e.stderr.decode()}",
                fg="red",
            )
            content = self.caddy_conf_path.read_text()
            log(f"Broken config content:\n{content}")
            raise
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            log(
                f"Warning: Could not validate caddy config: {e}",
                level=2,
                fg="yellow",
            )

    def reload_proxy(self) -> None:
        """Reload caddy to apply configuration changes.

        Attempts to reload caddy using available methods. Silently skips if:
        - Running in test environment (PYTEST_CURRENT_TEST set)
        - No reload mechanism is available
        - Commands fail (logs warning instead of raising)
        """
        # Skip reload in test environments
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return

        timeout = 5  # 5 second timeout to prevent hanging

        try:
            # Try supervisorctl with sudo (for containerized/supervised environments)
            result = subprocess.run(
                ["sudo", "-n", "supervisorctl", "restart", "caddy"],
                check=True,
                capture_output=True,
                timeout=timeout,
            )
            log("caddy reloaded via supervisorctl", level=2)
            return
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            pass  # Try next method

        try:
            # Fall back to systemctl (for systemd environments)
            subprocess.run(
                ["sudo", "-n", "systemctl", "reload", "caddy"],
                check=True,
                capture_output=True,
                timeout=timeout,
            )
            log("caddy reloaded via systemctl", level=2)
            return
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            pass  # Try next method

        try:
            # Fall back to caddy reload (direct caddy command)
            # Note: This requires the Caddy config to be in a specific location
            # or using the admin API
            subprocess.run(
                ["sudo", "-n", "caddy", "reload"],
                check=True,
                capture_output=True,
                timeout=timeout,
            )
            log("caddy reloaded via caddy reload command", level=2)
            return
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            pass  # All methods failed

        # Log warning if all methods failed
        log(
            "Warning: could not reload caddy automatically (all methods failed or timed out)",
            level=2,
            fg="yellow",
        )

    def setup_cache(self) -> None:
        """Configure Caddy caching for the application.

        Note: Caddy doesn't have built-in caching like Nginx.
        For production use, you may need to use a Caddy plugin or
        external caching layer. This method sets up basic cache headers.
        """
        self.env["HOP3_INTERNAL_CADDY_CACHE_MAPPINGS"] = ""

        # Check if caching is requested
        cache_prefixes = self.env.get("CADDY_CACHE_PREFIXES", "")
        if len(cache_prefixes):
            prefixes = []
            try:
                items = cache_prefixes.split(",")
                for item in items:
                    if item[0] == "/":
                        # Remove leading slash
                        prefixes.append(item[1:])
                    else:
                        prefixes.append(item)
                cache_prefixes = "|".join(prefixes)

                # Get cache timing parameters
                cache_time_control = self._get_cache_param(
                    "CACHE_CONTROL", "cache control", 3600
                )

                log(
                    f"caddy will set cache headers for /({cache_prefixes}) prefixes"
                    f" with max-age={cache_time_control}",
                    level=2,
                )

                # Expand cache mapping template
                self.env["HOP3_INTERNAL_CADDY_CACHE_MAPPINGS"] = expand_vars(
                    HOP3_INTERNAL_CADDY_CACHE_MAPPING,
                    {
                        "cache_prefixes": cache_prefixes,
                        "cache_time_control": cache_time_control,
                        "CADDY_BACKEND": self.env["CADDY_BACKEND"],
                    },
                )
            except Exception as e:
                log(
                    f"Error {e} in cache path spec: should be /prefix1:[,/prefix2],"
                    " ignoring.",
                )
                self.env["HOP3_INTERNAL_CADDY_CACHE_MAPPINGS"] = ""

    def _get_cache_param(self, key: str, name: str, default: int) -> int:
        """Get a cache parameter integer value from the environment.

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
