# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import json
import os
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from traceback import format_exc
from typing import Any
from urllib.request import urlopen

from click import secho as echo

from hop3.nginx.certificates import setup_certificates
from hop3.nginx.templates import (
    HOP3_INTERNAL_NGINX_CACHE_MAPPING,
    HOP3_INTERNAL_NGINX_STATIC_MAPPING,
    HOP3_INTERNAL_NGINX_UWSGI_SETTINGS,
    HOP3_INTERNAL_PROXY_CACHE_PATH,
    NGINX_COMMON_FRAGMENT,
    NGINX_HTTPS_ONLY_TEMPLATE,
    NGINX_PORTMAP_FRAGMENT,
    NGINX_TEMPLATE,
)
from hop3.system.constants import ACME_WWW, APP_ROOT, CACHE_ROOT, NGINX_ROOT
from hop3.util import command_output, get_boolean
from hop3.util.console import log
from hop3.util.templating import expand_vars


@dataclass(frozen=True)
class NginxConfig:
    env: dict[str, str]


def setup_nginx(app_name: str, env: dict[str, Any], workers: dict[str, str]) -> None:
    app_path = Path(APP_ROOT, app_name)

    # Hack to get around ClickCommand
    env["NGINX_SERVER_NAME"] = env["NGINX_SERVER_NAME"].split(",")
    env["NGINX_SERVER_NAME"] = " ".join(env["NGINX_SERVER_NAME"])

    nginx = command_output("nginx -V")

    nginx_ssl = "443 ssl"
    if "--with-http_v2_module" in nginx:
        nginx_ssl += " http2"
    elif (
        "--with-http_spdy_module" in nginx and "nginx/1.6.2" not in nginx
    ):  # avoid Raspbian bug
        nginx_ssl += " spdy"

    nginx_conf = os.path.join(NGINX_ROOT, f"{app_name}.conf")

    env.update(
        {  # lgtm [py/modification-of-default-value]
            "NGINX_SSL": nginx_ssl,
            "NGINX_ROOT": NGINX_ROOT,
            "ACME_WWW": ACME_WWW,
        }
    )

    # default to reverse proxying to the TCP port we picked
    env["HOP3_INTERNAL_NGINX_UWSGI_SETTINGS"] = (
        "proxy_pass http://{BIND_ADDRESS:s}:{PORT:s};".format(**env)
    )

    if "wsgi" in workers or "jwsgi" in workers:
        sock = os.path.join(NGINX_ROOT, f"{app_name}.sock")
        env["HOP3_INTERNAL_NGINX_UWSGI_SETTINGS"] = expand_vars(
            HOP3_INTERNAL_NGINX_UWSGI_SETTINGS, env
        )
        env["NGINX_SOCKET"] = env["BIND_ADDRESS"] = "unix://" + sock
        if "PORT" in env:
            del env["PORT"]
    else:
        env["NGINX_SOCKET"] = "{BIND_ADDRESS:s}:{PORT:s}".format(**env)
        echo(f"-----> nginx will look for app '{app_name}' on {env['NGINX_SOCKET']}")

    setup_certificates(app_name, env, nginx_conf)

    # restrict access to server from CloudFlare IP addresses
    acl = []
    if get_boolean(env.get("NGINX_CLOUDFLARE_ACL", "false")):
        try:
            cf = json.loads(
                urlopen("https://api.cloudflare.com/client/v4/ips")
                .read()
                .decode("utf-8")
            )
            if cf["success"] is True:
                for i in cf["result"]["ipv4_cidrs"]:
                    acl.append(f"allow {i};")
                if get_boolean(env.get("DISABLE_IPV6", "false")):
                    for i in cf["result"]["ipv6_cidrs"]:
                        acl.append(f"allow {i};")
                # allow access from controlling machine
                if "SSH_CLIENT" in os.environ:
                    remote_ip = os.environ["SSH_CLIENT"].split()[0]
                    echo(f"-----> nginx ACL will include your IP ({remote_ip})")
                    acl.append(f"allow {remote_ip};")
                acl.extend(["allow 127.0.0.1;", "deny all;"])
        except Exception:
            cf = defaultdict()
            echo(
                f"-----> Could not retrieve CloudFlare IP ranges: {format_exc()}",
                fg="red",
            )
    env["NGINX_ACL"] = " ".join(acl)
    env["HOP3_INTERNAL_NGINX_BLOCK_GIT"] = (
        "" if env.get("NGINX_ALLOW_GIT_FOLDERS") else r"location ~ /\.git { deny all; }"
    )

    # Configure Nginx caching
    env["HOP3_INTERNAL_PROXY_CACHE_PATH"] = ""
    env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = ""

    default_cache_path = os.path.join(CACHE_ROOT, app_name)
    if not os.path.exists(default_cache_path):
        os.makedirs(default_cache_path)
    try:
        _cache_size = int(env.get("NGINX_CACHE_SIZE", "1"))
    except Exception:
        echo("=====> Invalid cache size, defaulting to 1GB")
        _cache_size = 1

    cache_size = str(_cache_size) + "g"

    try:
        cache_time_control = int(env.get("NGINX_CACHE_CONTROL", "3600"))
    except Exception:
        echo("=====> Invalid time for cache control, defaulting to 3600s")
        cache_time_control = 3600
    cache_time_control = str(cache_time_control)

    try:
        cache_time_content = int(env.get("NGINX_CACHE_TIME", "3600"))
    except Exception:
        echo("=====> Invalid cache time for content, defaulting to 3600s")
        cache_time_content = 3600
    cache_time_content = str(cache_time_content) + "s"

    try:
        cache_time_redirects = int(env.get("NGINX_CACHE_REDIRECTS", "3600"))
    except Exception:
        echo("=====> Invalid cache time for redirects, defaulting to 3600s")
        cache_time_redirects = 3600
    cache_time_redirects = str(cache_time_redirects) + "s"

    try:
        cache_time_any = int(env.get("NGINX_CACHE_ANY", "3600"))
    except Exception:
        echo("=====> Invalid cache expiry fallback, defaulting to 3600s")
        cache_time_any = 3600
    cache_time_any = str(cache_time_any) + "s"

    try:
        cache_time_expiry = int(env.get("NGINX_CACHE_EXPIRY", "86400"))
    except Exception:
        echo("=====> Invalid cache expiry, defaulting to 86400s")
        cache_time_expiry = 86400
    cache_time_expiry = str(cache_time_expiry) + "s"

    cache_prefixes = env.get("NGINX_CACHE_PREFIXES", "")
    cache_path = env.get("NGINX_CACHE_PATH", default_cache_path)

    if not Path(cache_path).exists():
        log(
            f"Cache path {cache_path} does not exist, using default {default_cache_path}, be aware of disk usage.",
            level=4,
            fg="yellow",
        )
        cache_path = env.get(default_cache_path)

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
                f"-----> nginx will cache /({cache_prefixes}) prefixes up to {cache_time_expiry} or {cache_size} of disk space, with the following timings:"
            )
            echo(f"-----> nginx will cache content for {cache_time_content}.")
            echo(f"-----> nginx will cache redirects for {cache_time_redirects}.")
            echo(f"-----> nginx will cache everything else for {cache_time_any}.")
            echo(
                f"-----> nginx will send caching headers asking for {cache_time_control} seconds of public caching."
            )
            env["HOP3_INTERNAL_PROXY_CACHE_PATH"] = expand_vars(
                HOP3_INTERNAL_PROXY_CACHE_PATH, locals()
            )
            env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = expand_vars(
                HOP3_INTERNAL_NGINX_CACHE_MAPPING, locals()
            )
            env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = expand_vars(
                env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"], env
            )
        except Exception as e:
            echo(
                f"Error {e} in cache path spec: should be /prefix1:[,/prefix2], ignoring."
            )
            env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = ""

    env["HOP3_INTERNAL_NGINX_STATIC_MAPPINGS"] = ""
    # Get a mapping of /prefix1:path1,/prefix2:path2
    static_paths = env.get("NGINX_STATIC_PATHS", "")

    # prepend static worker path if present
    if "static" in workers:
        stripped = workers["static"].strip("/").rstrip("/")
        static_paths = (
            ("/" if stripped[0:1] == ":" else "/:")
            + (stripped if stripped else ".")
            + "/"
            + ("," if static_paths else "")
            + static_paths
        )
    if len(static_paths):
        try:
            items = static_paths.split(",")
            for item in items:
                static_url, static_path = item.split(":")
                if static_path[0] != "/":
                    static_path = os.path.join(app_path, static_path).rstrip("/") + "/"
                echo(f"-----> nginx will map {static_url} to {static_path}.")
                env["HOP3_INTERNAL_NGINX_STATIC_MAPPINGS"] = env[
                    "HOP3_INTERNAL_NGINX_STATIC_MAPPINGS"
                ] + expand_vars(HOP3_INTERNAL_NGINX_STATIC_MAPPING, locals())
        except Exception as e:
            echo(
                f"Error {e} in static path spec: should be /prefix1:path1[,/prefix2:path2], ignoring."
            )
            env["HOP3_INTERNAL_NGINX_STATIC_MAPPINGS"] = ""

    env["HOP3_INTERNAL_NGINX_CUSTOM_CLAUSES"] = (
        expand_vars(open(os.path.join(app_path, env["NGINX_INCLUDE_FILE"])).read(), env)
        if env.get("NGINX_INCLUDE_FILE")
        else ""
    )
    env["HOP3_INTERNAL_NGINX_PORTMAP"] = ""

    if (
        "web" in workers
        or "wsgi" in workers
        or "jwsgi" in workers
        or "rwsgi" in workers
    ):
        env["HOP3_INTERNAL_NGINX_PORTMAP"] = expand_vars(NGINX_PORTMAP_FRAGMENT, env)

    env["HOP3_INTERNAL_NGINX_COMMON"] = expand_vars(NGINX_COMMON_FRAGMENT, env)

    echo(
        f"-----> nginx will map app '{app_name}' to hostname(s) '{env['NGINX_SERVER_NAME']}'"
    )
    if get_boolean(env.get("NGINX_HTTPS_ONLY", "false")):
        buffer = expand_vars(NGINX_HTTPS_ONLY_TEMPLATE, env)
        echo(
            f"-----> nginx will redirect all requests to hostname(s) '{env['NGINX_SERVER_NAME']}' to HTTPS"
        )
    else:
        buffer = expand_vars(NGINX_TEMPLATE, env)

    # remove all references to IPv6 listeners (for enviroments where it's disabled)
    if get_boolean(env.get("DISABLE_IPV6", "false")):
        buffer = "\n".join(
            [line for line in buffer.split("\n") if "NGINX_IPV6" not in line]
        )

    # change any unecessary uWSGI specific directives to standard proxy ones
    if "wsgi" not in workers and "jwsgi" not in workers:
        buffer = buffer.replace("uwsgi_", "proxy_")

    # map Cloudflare connecting IP to REMOTE_ADDR
    if get_boolean(env.get("NGINX_CLOUDFLARE_ACL", "false")):
        buffer = buffer.replace(
            "REMOTE_ADDR $remote_addr", "REMOTE_ADDR $http_cf_connecting_ip"
        )
    with open(nginx_conf, "w") as h:
        h.write(buffer)

    # prevent broken config from breaking other deploys
    try:
        nginx_config_test = str(
            subprocess.check_output(
                f"nginx -t 2>&1 | grep {app_name}", env=os.environ, shell=True
            )
        )
    except Exception:
        nginx_config_test = None

    if nginx_config_test:
        echo(f"Error: [nginx config] {nginx_config_test}", fg="red")
        echo("Warning: removing broken nginx config.", fg="yellow")
        os.unlink(nginx_conf)
