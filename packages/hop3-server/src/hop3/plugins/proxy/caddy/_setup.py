# Copyright (c) 2016 Rui Carmo
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
from hop3.container import container
from hop3.core.protocols import Proxy
from hop3.lib import command_output, expand_vars, log
from hop3.services.certificates import CertificatesManager

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
class CaddyVirtualHost(Proxy):
    app: App
    env: Env
    workers: dict[str, str]

    def __post_init__(self) -> None:
        # Normalize server name list
        server_name_list = self.env["CADDY_SERVER_NAME"].split(",")
        # Caddy uses space-separated alternative names in the server block
        self.env["CADDY_SERVER_NAME"] = " ".join(server_name_list)

        # Check Caddy version
        try:
            caddy_version = command_output("caddy version")
            log(f"Using Caddy version: {caddy_version}", level=2)
        except Exception:
            log("Warning: Could not determine Caddy version", level=2, fg="yellow")

        self.env.update(
            {
                "CADDY_ROOT": str(CADDY_ROOT),
                "ACME_WWW": str(ACME_WWW),
                "CADDY_ACME_EMAIL": ACME_EMAIL,
            },
        )

    @property
    def app_name(self) -> str:
        return self.app.name

    @property
    def app_path(self) -> Path:
        return self.app.app_path

    @property
    def src_path(self) -> Path:
        return self.app.src_path

    def update_env(self, key: str, value: str = "", template: str = "") -> None:
        if template:
            value = template.format(**self.env)
        self.env[key] = value

    def setup(self) -> None:
        """Configures the Caddy environment for the application.

        This sets up the necessary environment variables and
        configurations for Caddy to properly serve the application,
        based on the application's configuration and deployment setup.
        """

        self.setup_backend()

        # Get certificates and add them to the caddy configuration
        self.setup_certificates()

        # Setup caching and static file handling
        self.setup_cache()
        self.setup_static()

        # Additional misc setup
        self.extra_setup()

        # Configure proxy settings and generate buffer with the configuration
        self.generate_config()

        # Check the generated Caddy configuration for errors
        self.check_config(self.caddy_conf_path)

        # Reload caddy to apply the new configuration
        self.reload_caddy()

    def setup_backend(self):
        """Configure the backend connection (TCP or Unix socket)."""
        # Check if using WSGI workers (which typically use Unix sockets)
        if "wsgi" in self.workers or "jwsgi" in self.workers:
            # Configure for Unix socket if WSGI or JWSGI workers are involved
            sock = CADDY_ROOT / f"{self.app_name}.sock"
            self.update_env("CADDY_BACKEND", f"unix/{sock}")
            self.update_env("BIND_ADDRESS", f"unix://{sock}")
            if "PORT" in self.env:
                del self.env["PORT"]
        else:
            # Configure for TCP connection
            bind_address = self.env.get("BIND_ADDRESS", "127.0.0.1")
            port = self.env.get("PORT", "8000")
            self.update_env("CADDY_BACKEND", f"{bind_address}:{port}")
            log(
                f"caddy will proxy app '{self.app_name}' to {bind_address}:{port}",
                level=2,
            )

    def setup_certificates(self) -> None:
        """Setup SSL certificates for the application."""
        domain_name = self.env["CADDY_SERVER_NAME"].split()[0]

        # Check if we should use automatic HTTPS or manual certificates
        use_auto_https = self.env.get_bool("CADDY_AUTO_HTTPS", False)

        if use_auto_https:
            # Use Caddy's automatic HTTPS with Let's Encrypt
            self.env["HOP3_INTERNAL_CADDY_TLS"] = expand_vars(CADDY_TLS_AUTO, self.env)
            log(
                f"caddy will use automatic HTTPS for '{domain_name}' via Let's Encrypt",
                level=2,
            )
        else:
            # Use manual certificates managed by hop3
            certificate_manager = container.get(CertificatesManager)
            certificate = certificate_manager.get_certificate(domain_name)
            (CADDY_ROOT / f"{self.app_name}.key").write_text(certificate.get_key())
            (CADDY_ROOT / f"{self.app_name}.crt").write_text(certificate.get_crt())
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
        if not self.env.get_bool("CADDY_DISABLE_COMPRESSION", False):
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
            f" '{self.env['CADDY_SERVER_NAME']}'",
            level=2,
        )

        # Choose template based on HTTPS-only setting
        if self.env.get_bool("CADDY_HTTPS_ONLY"):
            buffer = expand_vars(CADDY_HTTPS_ONLY_TEMPLATE, self.env)
            log(
                f"caddy will redirect all HTTP requests to HTTPS for"
                f" '{self.env['CADDY_SERVER_NAME']}'",
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

        for static_url, _static_path in static_paths:
            static_path = str(_static_path)
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

    def check_config(self, caddy_conf_path: Path) -> None:
        """Validate the Caddy configuration file.

        Input:
        - caddy_conf_path (Path): The path to the caddy configuration file to be checked.
        """
        import subprocess

        try:
            # Caddy can validate a specific config file
            subprocess.run(
                ["caddy", "validate", "--config", str(caddy_conf_path)],
                check=True,
                capture_output=True,
                timeout=5,
            )
            log(f"Caddy config validation passed for {caddy_conf_path}", level=2)
        except subprocess.CalledProcessError as e:
            log(
                f"Error: broken caddy config - {e.stderr.decode()}",
                fg="red",
            )
            content = caddy_conf_path.read_text()
            log(f"Broken config content:\n{content}")
            raise
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            log(
                f"Warning: Could not validate caddy config: {e}",
                level=2,
                fg="yellow",
            )

    def reload_caddy(self) -> None:
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

    def get_static_paths(self) -> list[tuple[str, Path]]:
        """Get a mapping of static URL prefixes to file system paths.

        Retrieves a mapping of URL prefixes to local file system paths
        for static content, based on environment configuration and worker settings.

        Returns:
            list of tuples: A list where each tuple contains a URL prefix as a string
            and the corresponding file system path as a Path object.
        """
        static_paths = self.env.get("CADDY_STATIC_PATHS", "")

        # prepend static worker path if present
        if "static" in self.workers:
            stripped = self.workers["static"].strip("/").rstrip("/")
            if stripped.startswith(":"):
                prefix = "/"
            else:
                prefix = "/:"

            if not stripped:
                stripped = "."

            if static_paths:
                separator = ","
            else:
                separator = ""

            static_paths = prefix + stripped + "/" + separator + static_paths

        if static_paths:
            items = static_paths.split(",")
        else:
            items = []

        result = []
        for item in items:
            static_url, static_path_str = item.split(":")
            static_path_str = static_path_str.rstrip()
            if static_path_str[0] == "/":
                # Use absolute path
                static_path = Path(static_path_str)
            else:
                # Use relative path based on src_path
                static_path = self.src_path / static_path_str
            result.append((static_url, static_path))

        return result

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
