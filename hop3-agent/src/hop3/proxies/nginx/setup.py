# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from traceback import format_exc
from typing import TYPE_CHECKING
from urllib.request import urlopen

from click import secho as echo

from hop3.system.constants import ACME_WWW, APP_ROOT, CACHE_ROOT, NGINX_ROOT
from hop3.util import command_output
from hop3.util.console import Abort, log
from hop3.util.templating import expand_vars

from .certificates import CertificatesManager
from .templates import (
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
    from hop3.core.env import Env


def setup_nginx(app_name: str, env: Env, workers: dict[str, str]) -> None:
    """Configure Nginx for an app."""
    config = NginxConfig(app_name, env, workers)
    config.setup()


@dataclass(frozen=True)
class NginxConfig:
    app_name: str
    env: Env[str, str]
    workers: dict[str, str]

    def __post_init__(self):
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
    def app_path(self) -> Path:
        return Path(APP_ROOT, self.app_name)

    def update_env(self, key: str, value: str = "", template: str = "") -> None:
        if template:
            value = template.format(**self.env)
        self.env[key] = value

    def setup(self):
        # default to reverse proxying to the TCP port we picked
        self.update_env(
            "HOP3_INTERNAL_NGINX_UWSGI_SETTINGS",
            template="proxy_pass http://{BIND_ADDRESS:s}:{PORT:s};",
        )
        # self.env["HOP3_INTERNAL_NGINX_UWSGI_SETTINGS"] = (
        #     "proxy_pass http://{BIND_ADDRESS:s}:{PORT:s};".format(**self.env)
        # )

        if "wsgi" in self.workers or "jwsgi" in self.workers:
            sock = os.path.join(NGINX_ROOT, f"{self.app_name}.sock")
            self.env["HOP3_INTERNAL_NGINX_UWSGI_SETTINGS"] = expand_vars(
                HOP3_INTERNAL_NGINX_UWSGI_SETTINGS,
                self.env,
            )
            self.update_env("NGINX_SOCKET", f"unix://{sock}")
            self.update_env("BIND_ADDRESS", f"unix://{sock}")
            if "PORT" in self.env:
                del self.env["PORT"]
        else:
            self.update_env("NGINX_SOCKET", template="{BIND_ADDRESS:s}:{PORT:s}")
            echo(
                f"-----> nginx will look for app '{self.app_name}' on {self.env['NGINX_SOCKET']}"
            )

        CertificatesManager(self.app_name, self.env).setup_certificates()

        self.setup_cloudflare()

        self.env["HOP3_INTERNAL_NGINX_BLOCK_GIT"] = (
            ""
            if self.env.get("NGINX_ALLOW_GIT_FOLDERS")
            else r"location ~ /\.git { deny all; }"
        )

        self.setup_cache()
        self.setup_static()

        buffer = self.setup_proxy()

        nginx_conf_path = Path(NGINX_ROOT, f"{self.app_name}.conf")
        nginx_conf_path.write_text(buffer)

        self.check_config(nginx_conf_path)

    def setup_proxy(self) -> str:
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

        # remove all references to IPv6 listeners (for enviroments where it's disabled)
        if self.env.get_bool("DISABLE_IPV6"):
            buffer = "\n".join(
                [line for line in buffer.split("\n") if "NGINX_IPV6" not in line],
            )

        # change any unecessary uWSGI specific directives to standard proxy ones
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
        self.env["HOP3_INTERNAL_NGINX_STATIC_MAPPINGS"] = ""

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
        # restrict access to server from CloudFlare IP addresses
        acl = []

        if self.env.get_bool("NGINX_CLOUDFLARE_ACL"):
            try:
                cf = json.loads(
                    urlopen("https://api.cloudflare.com/client/v4/ips")
                    .read()
                    .decode("utf-8"),
                )
            except Exception:
                raise Abort(
                    f"Could not retrieve CloudFlare IP ranges: {format_exc()}",
                )

            if cf["success"] is True:
                result = cf["result"]
                acl = [f"allow {i};" for i in result["ipv4_cidrs"]]

                if self.env.get_bool("DISABLE_IPV6"):
                    acl += [f"allow {i};" for i in result["ipv6_cidrs"]]

                # allow access from controlling machine
                if "SSH_CLIENT" in os.environ:
                    remote_ip = os.environ["SSH_CLIENT"].split()[0]
                    echo(f"-----> nginx ACL will include your IP ({remote_ip})")
                    acl += [f"allow {remote_ip};"]

                acl += ["allow 127.0.0.1;", "deny all;"]

        self.env["NGINX_ACL"] = " ".join(acl)

    def check_config(self, nginx_conf_path: Path) -> None:
        """Prevent broken config from breaking other deployments."""
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
        """Get a mapping of /prefix1:path1,/prefix2:path2"""
        static_paths = self.env.get("NGINX_STATIC_PATHS", "")

        # prepend static worker path if present
        if "static" in self.workers:
            stripped = self.workers["static"].strip("/").rstrip("/")
            static_paths = (
                ("/" if stripped[0:1] == ":" else "/:")
                + (stripped or ".")
                + "/"
                + ("," if static_paths else "")
                + static_paths
            )

        if static_paths:
            items = static_paths.split(",")
        else:
            items = []

        result = []
        for item in items:
            static_url, _static_path = item.split(":")
            _static_path = _static_path.rstrip()
            if _static_path[0] == "/":
                static_path = Path(_static_path)
            else:
                static_path = self.app_path / _static_path
            result.append((static_url, static_path))

        return result

    def expand_vars(self, tpl: str) -> str:
        return expand_vars(tpl, self.env)

    def setup_cache(self) -> None:
        """Configure Nginx caching"""
        self.env["HOP3_INTERNAL_PROXY_CACHE_PATH"] = ""
        self.env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = ""
        default_cache_path = os.path.join(CACHE_ROOT, self.app_name)
        if not os.path.exists(default_cache_path):
            os.makedirs(default_cache_path)

        try:
            _cache_size = self.env.get_int("NGINX_CACHE_SIZE", 1)
        except Exception:
            echo("=====> Invalid cache size, defaulting to 1GB")
            _cache_size = 1
        cache_size = str(_cache_size) + "g"

        try:
            _cache_time_control = self.env.get_int("NGINX_CACHE_CONTROL", 3600)
        except Exception:
            echo("=====> Invalid time for cache control, defaulting to 3600s")
            _cache_time_control = 3600
        cache_time_control = str(_cache_time_control)

        try:
            _cache_time_content = self.env.get_int("NGINX_CACHE_TIME", 3600)
        except Exception:
            echo("=====> Invalid cache time for content, defaulting to 3600s")
            _cache_time_content = 3600
        cache_time_content = str(_cache_time_content) + "s"

        try:
            _cache_time_redirects = self.env.get_int("NGINX_CACHE_REDIRECTS", 3600)
        except Exception:
            echo("=====> Invalid cache time for redirects, defaulting to 3600s")
            _cache_time_redirects = 3600
        cache_time_redirects = str(_cache_time_redirects) + "s"

        try:
            _cache_time_any = self.env.get_int("NGINX_CACHE_ANY", 3600)
        except Exception:
            echo("=====> Invalid cache expiry fallback, defaulting to 3600s")
            _cache_time_any = 3600
        cache_time_any = str(_cache_time_any) + "s"

        try:
            _cache_time_expiry = self.env.get_int("NGINX_CACHE_EXPIRY", 86400)
        except Exception:
            echo("=====> Invalid cache expiry, defaulting to 86400s")
            _cache_time_expiry = 86400
        cache_time_expiry = str(_cache_time_expiry) + "s"

        # FIXME
        cache_path = self.env.get_path("NGINX_CACHE_PATH", default_cache_path)
        if not cache_path.exists():
            log(
                f"Cache path {cache_path} does not exist, using default"
                f" {default_cache_path}, be aware of disk usage.",
                level=4,
                fg="yellow",
            )
            cache_path = self.env.get_path(default_cache_path)

        cache_prefixes = self.env.get("NGINX_CACHE_PREFIXES", "")
        if len(cache_prefixes):
            prefixes = []  # this will turn into part of /(path1|path2|path3)
            try:
                items = cache_prefixes.split(",")
                for item in items:
                    if item[0] == "/":
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
                self.env["HOP3_INTERNAL_PROXY_CACHE_PATH"] = expand_vars(
                    HOP3_INTERNAL_PROXY_CACHE_PATH,
                    locals(),
                )
                self.env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = expand_vars(
                    HOP3_INTERNAL_NGINX_CACHE_MAPPING,
                    locals(),
                )
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
