# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from traceback import format_exc
from typing import TYPE_CHECKING
from urllib.request import urlopen

from hop3.config.constants import ACME_WWW, CACHE_ROOT, NGINX_ROOT
from hop3.core.protocols import Proxy
from hop3.util import Abort, command_output, echo, expand_vars, log

from ._certificates import CertificatesManager
from ._templates import (
    HOP3_INTERNAL_NGINX_CACHE_MAPPING,
    HOP3_INTERNAL_NGINX_STATIC_MAPPING,
    HOP3_INTERNAL_NGINX_UWSGI_SETTINGS,
    HOP3_INTERNAL_PROXY_CACHE_PATH,
    NGINX_COMMON_FRAGMENT,
    NGINX_HTTPS_ONLY_TEMPLATE,
    NGINX_PORTMAP_FRAGMENT,
    NGINX_TEMPLATE,
)

if TYPE_CHECKING:
    from hop3.core.app import App
    from hop3.core.env import Env


@dataclass(frozen=True)
class Nginx(Proxy):
    app: App
    env: Env
    workers: dict[str, str]

    def __post_init__(self) -> None:
        # Hack to get around ClickCommand
        server_name_list = self.env["NGINX_SERVER_NAME"].split(",")
        self.env["NGINX_SERVER_NAME"] = " ".join(server_name_list)

        nginx_version = command_output("nginx -V")
        nginx_ssl = "443 ssl"
        if "--with-http_v2_module" in nginx_version:
            nginx_ssl += " http2"

        self.env.update(
            {
                "NGINX_SSL": nginx_ssl,
                "NGINX_ROOT": NGINX_ROOT,
                "ACME_WWW": ACME_WWW,
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
        """
        Configures the Nginx environment for the application.

        This sets up the necessary environment variables and configurations
        for Nginx to properly serve the application, based on the application's
        configuration and deployment setup.
        """

        # default to reverse proxying to the TCP port we picked
        self.update_env(
            "HOP3_INTERNAL_NGINX_UWSGI_SETTINGS",
            template="proxy_pass http://{BIND_ADDRESS:s}:{PORT:s};",
        )
        # self.env["HOP3_INTERNAL_NGINX_UWSGI_SETTINGS"] = (
        #     "proxy_pass http://{BIND_ADDRESS:s}:{PORT:s};".format(**self.env)
        # )

        if "wsgi" in self.workers or "jwsgi" in self.workers:
            # Configure for Unix socket if WSGI or JWSGI workers are involved
            sock = NGINX_ROOT / f"{self.app_name}.sock"
            self.env["HOP3_INTERNAL_NGINX_UWSGI_SETTINGS"] = expand_vars(
                HOP3_INTERNAL_NGINX_UWSGI_SETTINGS,
                self.env,
            )
            self.update_env("NGINX_SOCKET", f"unix://{sock}")
            self.update_env("BIND_ADDRESS", f"unix://{sock}")
            if "PORT" in self.env:
                del self.env["PORT"]
        else:
            # Configure for TCP socket if no WSGI or JWSGI workers are involved
            self.update_env("NGINX_SOCKET", template="{BIND_ADDRESS:s}:{PORT:s}")
            echo(
                f"-----> nginx will look for app '{self.app_name}' on {self.env['NGINX_SOCKET']}"
            )

        # Initialize CertificatesManager and setup certificates
        CertificatesManager(self.app_name, dict(**self.env)).setup_certificates()

        # Setup Cloudflare configurations if necessary
        self.setup_cloudflare()

        # Conditionally block .git folders from being served
        self.env["HOP3_INTERNAL_NGINX_BLOCK_GIT"] = (
            ""
            if self.env.get("NGINX_ALLOW_GIT_FOLDERS")
            else r"location ~ /\.git { deny all; }"
        )

        # Setup caching and static file handling
        self.setup_cache()
        self.setup_static()

        # Configure proxy settings and generate buffer with the configuration
        buffer = self.setup_proxy()

        # Write the generated Nginx configuration to a file
        nginx_conf_path = NGINX_ROOT / f"{self.app_name}.conf"
        nginx_conf_path.write_text(buffer)

        # Check the generated Nginx configuration for errors
        self.check_config(nginx_conf_path)

    def setup_proxy(self) -> str:
        """
        Configures and returns the nginx configuration buffer based on
        specified workers and environment variables.

        Sets up nginx proxy configurations by expanding
        certain template variables using environment settings and
        adjusts the buffer based on conditions like HTTPS-only
        redirection, IPv6 disabling, uWSGI directives, and Cloudflare
        IP mapping.
        """
        if (
            "web" in self.workers
            or "wsgi" in self.workers
            or "jwsgi" in self.workers
            or "rwsgi" in self.workers
        ):
            self.env["HOP3_INTERNAL_NGINX_PORTMAP"] = expand_vars(
                NGINX_PORTMAP_FRAGMENT, self.env
            )
        self.env["HOP3_INTERNAL_NGINX_COMMON"] = expand_vars(
            NGINX_COMMON_FRAGMENT, self.env
        )
        echo(
            f"-----> nginx will map app '{self.app_name}' to hostname(s)"
            f" '{self.env['NGINX_SERVER_NAME']}'",
        )
        if self.env.get_bool("NGINX_HTTPS_ONLY"):
            buffer = expand_vars(NGINX_HTTPS_ONLY_TEMPLATE, self.env)
            echo(
                "-----> nginx will redirect all requests to hostname(s)"
                f" '{self.env['NGINX_SERVER_NAME']}' to HTTPS",
            )
        else:
            buffer = expand_vars(NGINX_TEMPLATE, self.env)

        # remove all references to IPv6 listeners (for environments where it's disabled)
        if self.env.get_bool("DISABLE_IPV6"):
            buffer = "\n".join(
                [line for line in buffer.split("\n") if "NGINX_IPV6" not in line],
            )

        # change any unnecessary uWSGI specific directives to standard proxy ones
        if "wsgi" not in self.workers and "jwsgi" not in self.workers:
            buffer = buffer.replace("uwsgi_", "proxy_")

        # map Cloudflare connecting IP to REMOTE_ADDR
        if self.env.get_bool("NGINX_CLOUDFLARE_ACL"):
            buffer = buffer.replace(
                "REMOTE_ADDR $remote_addr",
                "REMOTE_ADDR $http_cf_connecting_ip",
            )
        return buffer

    def setup_static(self) -> None:
        """
        Configures static path mappings for an NGINX server in the environment configuration.
        """
        self.env["HOP3_INTERNAL_NGINX_STATIC_MAPPINGS"] = (
            ""  # Initialize the static mappings string in the environment
        )

        static_paths = self.get_static_paths()

        for static_url, _static_path in static_paths:
            static_path = str(_static_path)
            echo(f"-----> nginx will map {static_url} to {static_path}.")
            self.env["HOP3_INTERNAL_NGINX_STATIC_MAPPINGS"] += expand_vars(
                HOP3_INTERNAL_NGINX_STATIC_MAPPING,
                locals(),
            )

        if nginx_include_file := self.env.get("NGINX_INCLUDE_FILE"):
            tpl = Path(self.app_path, nginx_include_file).read_text()
        else:
            tpl = ""
        self.env["HOP3_INTERNAL_NGINX_CUSTOM_CLAUSES"] = self.expand_vars(tpl)

        self.env["HOP3_INTERNAL_NGINX_PORTMAP"] = ""

    def setup_cloudflare(self) -> None:
        """
        Configure access control to the server based on CloudFlare IP addresses.

        Sets up an access control list (ACL) for the server using
        CloudFlare's IP ranges. It allows traffic from CloudFlare IPs and possibly
        the controlling machine's IP, while denying all other traffic.
        """
        # restrict access to server from CloudFlare IP addresses
        acl = []

        if self.env.get_bool("NGINX_CLOUDFLARE_ACL"):
            try:
                # Retrieve CloudFlare IP ranges
                cf = json.loads(
                    urlopen("https://api.cloudflare.com/client/v4/ips")
                    .read()
                    .decode("utf-8"),
                )
            except Exception:
                # Handle exceptions by raising an Abort with a formatted error message
                msg = f"Could not retrieve CloudFlare IP ranges: {format_exc()}"
                raise Abort(msg)

            if cf["success"] is True:
                result = cf["result"]
                acl = [f"allow {i};" for i in result["ipv4_cidrs"]]

                if self.env.get_bool("DISABLE_IPV6"):
                    # Include IPv6 addresses if not disabled
                    acl += [f"allow {i};" for i in result["ipv6_cidrs"]]

                # allow access from controlling machine
                if "SSH_CLIENT" in os.environ:
                    remote_ip = os.environ["SSH_CLIENT"].split()[0]
                    echo(f"-----> nginx ACL will include your IP ({remote_ip})")
                    acl += [f"allow {remote_ip};"]

                acl += ["allow 127.0.0.1;", "deny all;"]

        self.env["NGINX_ACL"] = " ".join(acl)

    def check_config(self, nginx_conf_path: Path) -> None:
        """
        Prevent broken config from breaking other deployments.

        Input:
        - nginx_conf_path (Path): The path to the nginx configuration file to be checked.
        """
        # FIXME: currently broken (should be run as root)
        return

        # try:
        #     subprocess.check_output(["/usr/sbin/nginx", "-t"])
        # except subprocess.CalledProcessError:
        #     echo(f"Error: broken nginx config - removing", fg="red")
        #     content = nginx_conf_path.read_text()
        #     echo(f"here is the broken config\n{content}")
        #     # nginx_conf_path.unlink()
        #     sys.exit(1)

    def get_static_paths(self) -> list[tuple[str, Path]]:
        """Get a mapping of static URL prefixes to file system paths.

        Retrieves a mapping of URL prefixes to local file system paths
        for static content, based on environment configuration and worker settings.

        Returns:
            list of tuples: A list where each tuple contains a URL prefix as a string
            and the corresponding file system path as a Path object.
        """
        static_paths = self.env.get("NGINX_STATIC_PATHS", "")

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
            static_url, _static_path = item.split(":")
            _static_path = _static_path.rstrip()
            if _static_path[0] == "/":
                # Use absolute path
                static_path = Path(_static_path)
            else:
                # Use relative path based on src_path
                static_path = self.src_path / _static_path
            result.append((static_url, static_path))

        return result

    def expand_vars(self, template: str) -> str:
        """
        Expand variables in a template string using the environment of the current object.

        Input:
        - template (str): The template string containing variables to be expanded.

        Returns:
        - str: The resulting string with all variables expanded based on the object's environment.
        """
        return expand_vars(template, self.env)

    def setup_cache(self) -> None:
        """
        Configure Nginx caching for the application.

        This sets up caching preferences and paths for Nginx by
        retrieving caching parameters, managing cache paths, and setting
        environment variables for internal proxies.
        """
        self.env["HOP3_INTERNAL_PROXY_CACHE_PATH"] = ""
        self.env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = ""

        default_cache_path = CACHE_ROOT / self.app_name
        if not default_cache_path.exists():
            default_cache_path.mkdir(parents=True)

        # Retrieve various cache parameters with defaults
        cache_size = self._get_cache_param("CACHE_SIZE", "cache size", 1, "g")
        cache_time_control = self._get_cache_param(
            "CACHE_CONTROL", "cache control", 3600, "s"
        )
        cache_time_content = self._get_cache_param(
            "CACHE_TIME", "cache time", 3600, "s"
        )
        cache_time_redirects = self._get_cache_param(
            "CACHE_REDIRECTS", "cache redirects", 3600, "s"
        )
        cache_time_any = self._get_cache_param(
            "CACHE_ANY", "cache expiry fallback", 3600, "s"
        )
        cache_time_expiry = self._get_cache_param(
            "CACHE_EXPIRY", "cache expiry", 86400, "s"
        )

        # Determine the cache path and create directory if it doesn't exist
        cache_path = self.env.get_path("NGINX_CACHE_PATH", default_cache_path)
        if not cache_path.exists():
            log(
                f"Cache path {cache_path} does not exist, using default"
                f" {default_cache_path}, be aware of disk usage.",
                level=4,
                fg="yellow",
            )
            cache_path = default_cache_path

        cache_prefixes = self.env.get("NGINX_CACHE_PREFIXES", "")
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
                echo(
                    f"-----> nginx will cache /({cache_prefixes}) prefixes up to"
                    f" {cache_time_expiry} or {cache_size} of disk space, with the"
                    " following timings:",
                )
                echo(f"-----> nginx will cache content for {cache_time_content}.")
                echo(f"-----> nginx will cache redirects for {cache_time_redirects}.")
                echo(f"-----> nginx will cache everything else for {cache_time_any}.")
                echo(
                    "-----> nginx will send caching headers asking for"
                    f" {cache_time_control} seconds of public caching.",
                )
                # Expand environment variables with current local variables
                self.env["HOP3_INTERNAL_PROXY_CACHE_PATH"] = expand_vars(
                    HOP3_INTERNAL_PROXY_CACHE_PATH,
                    locals(),
                )
                self.env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = expand_vars(
                    HOP3_INTERNAL_NGINX_CACHE_MAPPING,
                    locals(),
                )
                # Further expand using environment variables
                self.env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = expand_vars(
                    self.env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"],
                    self.env,
                )
            except Exception as e:
                echo(
                    f"Error {e} in cache path spec: should be /prefix1:[,/prefix2],"
                    " ignoring.",
                )
                self.env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = ""

    def _get_cache_param(self, key: str, name: str, default: int, suffix: str) -> str:
        """
        Generate a cache parameter string by retrieving an integer value from the environment.

        This attempts to fetch an integer value from the environment using a key prefixed
        with "NGINX_". If it fails to fetch or the fetched value is invalid, it logs a message and
        defaults to the provided default value. The resulting integer is then converted to a string
        with a specified suffix.

        Input:
        - key (str): The key to look up in the environment, prefixed with "NGINX_".
        - name (str): The name of the parameter, used for logging in case of an error.
        - default (int): The default integer value to use if retrieval from the environment fails.
        - suffix (str): The string suffix to append to the retrieved or default integer value.

        Returns:
        - str: The resulting string composed of the fetched or default integer value and the suffix.
        """
        try:
            return str(self.env.get_int("NGINX_" + key, default)) + suffix
        except Exception:
            echo(f"=====> Invalid {name}, defaulting to {default}{suffix}")
            return str(default) + suffix