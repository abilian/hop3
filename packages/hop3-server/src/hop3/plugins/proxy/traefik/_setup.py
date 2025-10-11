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

from hop3.config import ACME_EMAIL, ACME_WWW, TRAEFIK_ROOT
from hop3.container import container
from hop3.core.protocols import Proxy
from hop3.lib import command_output, expand_vars, log
from hop3.services.certificates import CertificatesManager

from ._templates import (
    HOP3_INTERNAL_TRAEFIK_CACHE_MIDDLEWARE,
    HOP3_INTERNAL_TRAEFIK_STATIC_ROUTER,
    HOP3_INTERNAL_TRAEFIK_STATIC_SERVICE,
    TRAEFIK_BLOCK_GIT_MIDDLEWARE,
    TRAEFIK_HEADERS_MIDDLEWARE,
    TRAEFIK_HTTPS_ONLY_TEMPLATE,
    TRAEFIK_TEMPLATE,
    TRAEFIK_TLS_MANUAL,
)

if TYPE_CHECKING:
    from hop3.core.env import Env
    from hop3.orm import App


@dataclass(frozen=True)
class TraefikVirtualHost(Proxy):
    app: App
    env: Env
    workers: dict[str, str]

    def __post_init__(self) -> None:
        # Normalize server name list (Traefik supports multiple hosts with backticks)
        server_name_list = self.env["TRAEFIK_SERVER_NAME"].split(",")
        # For Traefik, we'll use the first domain as primary
        self.env["TRAEFIK_SERVER_NAME"] = server_name_list[0].strip()

        # Check Traefik version
        try:
            traefik_version = command_output("traefik version")
            log(f"Using Traefik version: {traefik_version}", level=2)
        except Exception:
            log("Warning: Could not determine Traefik version", level=2, fg="yellow")

        self.env.update(
            {
                "TRAEFIK_ROOT": str(TRAEFIK_ROOT),
                "ACME_WWW": str(ACME_WWW),
                "TRAEFIK_ACME_EMAIL": ACME_EMAIL,
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
        """Configures the Traefik environment for the application.

        This sets up the necessary environment variables and
        configurations for Traefik to properly serve the application,
        based on the application's configuration and deployment setup.
        """

        self.setup_backend()

        # Get certificates and add them to the traefik configuration
        self.setup_certificates()

        # Setup caching and static file handling
        self.setup_cache()
        self.setup_static()

        # Additional misc setup
        self.extra_setup()

        # Configure proxy settings and generate buffer with the configuration
        self.generate_config()

        # Check the generated Traefik configuration for errors
        self.check_config(self.traefik_conf_path)

        # Reload traefik to apply the new configuration
        self.reload_traefik()

    def setup_backend(self):
        """Configure the backend connection (TCP or Unix socket)."""
        # Check if using WSGI workers (which typically use Unix sockets)
        if "wsgi" in self.workers or "jwsgi" in self.workers:
            # Configure for Unix socket if WSGI or JWSGI workers are involved
            sock = TRAEFIK_ROOT / f"{self.app_name}.sock"
            # Traefik requires http:// scheme even for unix sockets
            self.update_env("TRAEFIK_BACKEND", f"http://unix:{sock}")
            self.update_env("BIND_ADDRESS", f"unix://{sock}")
            if "PORT" in self.env:
                del self.env["PORT"]
        else:
            # Configure for TCP connection
            bind_address = self.env.get("BIND_ADDRESS", "127.0.0.1")
            port = self.env.get("PORT", "8000")
            self.update_env("TRAEFIK_BACKEND", f"http://{bind_address}:{port}")
            log(
                f"traefik will proxy app '{self.app_name}' to {bind_address}:{port}",
                level=2,
            )

    def setup_certificates(self) -> None:
        """Setup SSL certificates for the application."""
        domain_name = self.env["TRAEFIK_SERVER_NAME"].split()[0]

        # Check if we should use automatic HTTPS or manual certificates
        use_auto_https = self.env.get_bool("TRAEFIK_AUTO_HTTPS", True)

        if use_auto_https:
            # Use Traefik's automatic HTTPS with Let's Encrypt
            # This is configured in the main Traefik config, not per-app
            self.env["HOP3_INTERNAL_TRAEFIK_TLS"] = ""
            log(
                f"traefik will use automatic HTTPS for '{domain_name}' via Let's Encrypt",
                level=2,
            )
        else:
            # Use manual certificates managed by hop3
            certificate_manager = container.get(CertificatesManager)
            certificate = certificate_manager.get_certificate(domain_name)
            (TRAEFIK_ROOT / f"{self.app_name}.key").write_text(certificate.get_key())
            (TRAEFIK_ROOT / f"{self.app_name}.crt").write_text(certificate.get_crt())
            self.env["HOP3_INTERNAL_TRAEFIK_TLS"] = expand_vars(
                TRAEFIK_TLS_MANUAL, self.env
            )
            log(
                f"traefik will use manual certificates for '{domain_name}'",
                level=2,
            )

    def extra_setup(self):
        """Additional configuration setup."""
        middlewares = []

        # Conditionally block .git folders from being served
        if not self.env.get("TRAEFIK_ALLOW_GIT_FOLDERS"):
            self.env["HOP3_INTERNAL_TRAEFIK_BLOCK_GIT"] = expand_vars(
                TRAEFIK_BLOCK_GIT_MIDDLEWARE, self.env
            )
            middlewares.append(f"- {self.app_name}-block-git")
        else:
            self.env["HOP3_INTERNAL_TRAEFIK_BLOCK_GIT"] = ""

        # Add custom headers middleware
        self.env["HOP3_INTERNAL_TRAEFIK_HEADERS"] = expand_vars(
            TRAEFIK_HEADERS_MIDDLEWARE, self.env
        )
        middlewares.append(f"- {self.app_name}-headers")

        # Set middlewares list
        self.env["HOP3_INTERNAL_TRAEFIK_MIDDLEWARES"] = "\n        ".join(middlewares)

        # Initialize custom middlewares
        self.env["HOP3_INTERNAL_TRAEFIK_CUSTOM_MIDDLEWARES"] = ""

        self.env["TRAEFIK_ACL"] = ""

    def generate_config(self) -> None:
        """Generate the Traefik YAML configuration."""
        buffer = self.get_proxy_conf()
        self.traefik_conf_path.write_text(buffer)
        log(f"Generated Traefik config at {self.traefik_conf_path}", level=2)

    @property
    def traefik_conf_path(self) -> Path:
        """Path to the Traefik configuration file for this app."""
        return TRAEFIK_ROOT / f"{self.app_name}.yml"

    def get_proxy_conf(self) -> str:
        """Returns the traefik configuration buffer based on
        specified workers and environment variables.

        Sets up traefik proxy configurations by expanding certain template
        variables using environment settings and adjusts the buffer
        based on conditions like HTTPS-only redirection.
        """
        log(
            f"traefik will serve app '{self.app_name}' on hostname(s)"
            f" '{self.env['TRAEFIK_SERVER_NAME']}'",
            level=2,
        )

        # Choose template based on HTTPS-only setting
        if self.env.get_bool("TRAEFIK_HTTPS_ONLY"):
            buffer = expand_vars(TRAEFIK_HTTPS_ONLY_TEMPLATE, self.env)
            log(
                f"traefik will redirect all HTTP requests to HTTPS for"
                f" '{self.env['TRAEFIK_SERVER_NAME']}'",
                level=2,
            )
        else:
            buffer = expand_vars(TRAEFIK_TEMPLATE, self.env)

        # Add TLS configuration if using manual certificates
        if self.env.get("HOP3_INTERNAL_TRAEFIK_TLS"):
            buffer += "\n" + self.env["HOP3_INTERNAL_TRAEFIK_TLS"]

        return buffer

    def setup_static(self) -> None:
        """Configures static path mappings for a Traefik server in the
        environment configuration."""
        static_routers = []
        static_services = []

        static_paths = self.get_static_paths()

        for idx, (static_url, _static_path) in enumerate(static_paths):
            static_path = str(_static_path)
            static_index = idx
            log(
                f"traefik will serve static files from {static_url} -> {static_path}",
                level=2,
            )

            # Create router and service for each static path
            router = expand_vars(
                HOP3_INTERNAL_TRAEFIK_STATIC_ROUTER,
                {
                    **self.env,
                    "static_url": static_url,
                    "static_path": static_path,
                    "static_index": static_index,
                    "APP": self.app_name,
                    "TRAEFIK_SERVER_NAME": self.env["TRAEFIK_SERVER_NAME"],
                },
            )
            service = expand_vars(
                HOP3_INTERNAL_TRAEFIK_STATIC_SERVICE,
                {
                    **self.env,
                    "static_path": static_path,
                    "static_index": static_index,
                    "APP": self.app_name,
                },
            )

            static_routers.append(router)
            static_services.append(service)

        self.env["HOP3_INTERNAL_TRAEFIK_STATIC_ROUTERS"] = "".join(static_routers)
        self.env["HOP3_INTERNAL_TRAEFIK_STATIC_SERVICES"] = "".join(static_services)

        # Include custom Traefik configuration if specified
        if traefik_include_file := self.env.get("TRAEFIK_INCLUDE_FILE"):
            tpl = Path(self.app_path, traefik_include_file).read_text()
            self.env["HOP3_INTERNAL_TRAEFIK_CUSTOM_CONFIG"] = expand_vars(tpl, self.env)
        else:
            self.env["HOP3_INTERNAL_TRAEFIK_CUSTOM_CONFIG"] = ""

    def check_config(self, traefik_conf_path: Path) -> None:
        """Validate the Traefik configuration file.

        Input:
        - traefik_conf_path (Path): The path to the traefik configuration file to be checked.
        """
        # Traefik doesn't have a built-in validate command for individual files
        # We can do basic YAML syntax checking
        try:
            import yaml

            with open(traefik_conf_path) as f:
                yaml.safe_load(f)
            log(f"Traefik config validation passed for {traefik_conf_path}", level=2)
        except ImportError:
            log(
                "Warning: PyYAML not installed, skipping config validation",
                level=2,
                fg="yellow",
            )
        except yaml.YAMLError as e:
            log(
                f"Error: invalid YAML in traefik config - {e}",
                fg="red",
            )
            content = traefik_conf_path.read_text()
            log(f"Broken config content:\n{content}")
            raise
        except Exception as e:
            log(
                f"Warning: Could not validate traefik config: {e}",
                level=2,
                fg="yellow",
            )

    def reload_traefik(self) -> None:
        """Reload traefik to apply configuration changes.

        Attempts to reload traefik using available methods. Silently skips if:
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
            subprocess.run(
                ["sudo", "-n", "supervisorctl", "restart", "traefik"],
                check=True,
                capture_output=True,
                timeout=timeout,
            )
            log("traefik reloaded via supervisorctl", level=2)
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
                ["sudo", "-n", "systemctl", "reload", "traefik"],
                check=True,
                capture_output=True,
                timeout=timeout,
            )
            log("traefik reloaded via systemctl", level=2)
            return
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            pass  # Try next method

        # Traefik typically watches config files and reloads automatically
        # So if the above methods fail, it's likely running in file-watch mode
        log(
            "Note: Traefik may auto-reload config files if file watching is enabled",
            level=2,
        )

    def get_static_paths(self) -> list[tuple[str, Path]]:
        """Get a mapping of static URL prefixes to file system paths.

        Retrieves a mapping of URL prefixes to local file system paths
        for static content, based on environment configuration and worker settings.

        Returns:
            list of tuples: A list where each tuple contains a URL prefix as a string
            and the corresponding file system path as a Path object.
        """
        static_paths = self.env.get("TRAEFIK_STATIC_PATHS", "")

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
        """Configure Traefik caching for the application.

        Note: Traefik doesn't have built-in caching like Nginx.
        This method sets up cache headers via middleware.
        For actual caching, you'd need a Traefik plugin or external cache.
        """
        # Check if caching headers are requested
        cache_time_control = self.env.get_int("TRAEFIK_CACHE_CONTROL", 0)

        if cache_time_control > 0:
            log(
                f"traefik will set cache headers with max-age={cache_time_control}",
                level=2,
            )

            # Add cache middleware to custom middlewares
            cache_middleware = expand_vars(
                HOP3_INTERNAL_TRAEFIK_CACHE_MIDDLEWARE,
                {"cache_time_control": cache_time_control, "APP": self.app_name},
            )

            if self.env.get("HOP3_INTERNAL_TRAEFIK_CUSTOM_MIDDLEWARES"):
                self.env["HOP3_INTERNAL_TRAEFIK_CUSTOM_MIDDLEWARES"] += cache_middleware
            else:
                self.env["HOP3_INTERNAL_TRAEFIK_CUSTOM_MIDDLEWARES"] = cache_middleware

            # Add to middlewares list
            middlewares = self.env.get("HOP3_INTERNAL_TRAEFIK_MIDDLEWARES", "")
            if middlewares:
                middlewares += f"\n        - {self.app_name}-cache-headers"
            else:
                middlewares = f"- {self.app_name}-cache-headers"
            self.env["HOP3_INTERNAL_TRAEFIK_MIDDLEWARES"] = middlewares
