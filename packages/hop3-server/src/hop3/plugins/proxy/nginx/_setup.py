# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.config import ACME_WWW, CACHE_ROOT, NGINX_ROOT
from hop3.core.identifiers import validate_hostname_list
from hop3.core.protocols import BaseProxy
from hop3.di import create_container
from hop3.lib import (
    Diagnosis,
    abort_with_diagnosis,
    command_output,
    expand_vars,
    log,
    log_diagnosis,
)
from hop3.lib.rootd import (
    LocalRootdClient,
    RootdOpError,
    RootdUnavailableError,
)
from hop3.platform.certificates import (
    CertificatesManager,
    verify_cert,
    write_private_key,
)

from ._templates import (
    HOP3_INTERNAL_NGINX_CACHE_MAPPING,
    HOP3_INTERNAL_NGINX_STATIC_MAPPING,
    HOP3_INTERNAL_PROXY_CACHE_PATH,
    NGINX_COMMON_FRAGMENT,
    NGINX_HTTPS_ONLY_TEMPLATE,
    NGINX_PORTMAP_FRAGMENT,
    NGINX_TEMPLATE,
)

if TYPE_CHECKING:
    from hop3.core.env import Env
    from hop3.orm import App


@dataclass(frozen=True)
class NginxVirtualHost(BaseProxy):
    app: App
    env: Env
    workers: dict[str, str]

    def get_proxy_name(self) -> str:
        """Return the proxy name for environment variable construction."""
        return "nginx"

    def __post_init__(self) -> None:
        # Validate each host in HOST_NAME before it lands in the nginx config.
        # The proxy template interpolates HOST_NAME straight into
        # `server_name $HOST_NAME;`, so an un-validated value with a newline
        # or `;` would inject arbitrary nginx directives.
        server_name_list = validate_hostname_list(self.env["HOST_NAME"])
        self.env["HOST_NAME"] = " ".join(server_name_list) or "_"

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

    def setup_backend(self):
        # For static-only apps, skip backend configuration entirely
        # (they serve files directly without a backend process)
        if len(self.workers) == 1 and "static" in self.workers:
            self.env["HOP3_INTERNAL_NGINX_UWSGI_SETTINGS"] = ""
            self.env["HOP3_INTERNAL_NGINX_PORTMAP"] = ""
            # Set a dummy NGINX_SOCKET to prevent template errors
            # (it won't be used since we remove the upstream block later)
            self.env["NGINX_SOCKET"] = ""
            # Mark this as a static-only app for template generation
            self.env["HOP3_STATIC_ONLY"] = "1"
            log(
                f"nginx will serve static files directly for '{self.app_name}' (no backend process)",
                level=2,
            )
            return

        # Always use HTTP proxy_pass for all workers (including WSGI)
        # This allows direct HTTP access for development, debugging, and health checks
        # uWSGI listens on HTTP sockets, and nginx proxies to them
        self.update_env(
            "HOP3_INTERNAL_NGINX_UWSGI_SETTINGS",
            template="proxy_pass http://{BIND_ADDRESS:s}:{PORT:s};",
        )
        self.update_env("NGINX_SOCKET", template="{BIND_ADDRESS:s}:{PORT:s}")
        log(
            f"nginx will proxy to app '{self.app_name}' on http://{self.env['BIND_ADDRESS']}:{self.env['PORT']}",
            level=2,
        )

    def setup_certificates(self) -> None:
        domain_name = self.env["HOST_NAME"].split()[0]

        # Engine choice (self-signed vs certbot) and the public-FQDN gate live in
        # select_engine (via get_certificate): the catch-all "_", bare app names,
        # and any non-public host get self-signed there, while a real public
        # domain — even on a static or docker app — gets a CA cert. No per-proxy
        # special-casing, and never a silent self-sign of a public domain.
        container = create_container()
        try:
            certificate_manager = container.get(CertificatesManager)
            certificate = certificate_manager.get_certificate(domain_name)
            write_private_key(
                NGINX_ROOT / f"{self.app_name}.key", certificate.get_key()
            )
            (NGINX_ROOT / f"{self.app_name}.crt").write_text(certificate.get_crt())
            # Post-condition: a bad cert (expired, wrong domain, or silently
            # self-signed for a public domain) fails the deploy loudly instead
            # of quietly serving an untrusted/expired cert.
            verify_cert(domain_name)
        finally:
            container.close()

    def extra_setup(self):
        # Conditionally block .git folders from being served
        self.env["HOP3_INTERNAL_NGINX_BLOCK_GIT"] = (
            ""
            if self.env.get("NGINX_ALLOW_GIT_FOLDERS")
            else r"location ~ /\.git { deny all; }"
        )
        self.env["NGINX_ACL"] = ""

    def generate_config(self) -> None:
        buffer = self.get_proxy_conf()
        self.nginx_conf_path.write_text(buffer)

    @property
    def nginx_conf_path(self) -> Path:
        return NGINX_ROOT / f"{self.app_name}.conf"

    def get_proxy_conf(self) -> str:
        """Returns the nginx configuration buffer based on
        specified workers and environment variables.

        Sets up nginx proxy configurations by expanding certain template
        variables using environment settings and adjusts the buffer
        based on conditions like HTTPS-only redirection, IPv6 disabling,
        uWSGI directives, and Cloudflare IP mapping.
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
        log(
            f"nginx will map app '{self.app_name}' to hostname(s)"
            f" '{self.env['HOST_NAME']}'",
            level=2,
        )
        if self.env.get_bool("NGINX_HTTPS_ONLY"):
            buffer = expand_vars(NGINX_HTTPS_ONLY_TEMPLATE, self.env)
            log(
                "nginx will redirect all requests to hostname(s)"
                f" '{self.env['HOST_NAME']}' to HTTPS",
                level=2,
            )
        else:
            buffer = expand_vars(NGINX_TEMPLATE, self.env)

        # For static-only apps, remove the upstream block entirely
        # (static files are served directly without a backend)
        if self.env.get("HOP3_STATIC_ONLY"):
            # Remove lines from "upstream $APP {" to the closing "}"
            lines = buffer.split("\n")
            filtered_lines = []
            in_upstream = False
            for line in lines:
                if line.strip().startswith("upstream "):
                    in_upstream = True
                    continue
                if in_upstream:
                    if line.strip() == "}":
                        in_upstream = False
                    continue
                filtered_lines.append(line)
            buffer = "\n".join(filtered_lines)

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
        """Configures static path mappings for an NGINX server in the
        environment configuration."""
        self.env["HOP3_INTERNAL_NGINX_STATIC_MAPPINGS"] = (
            ""  # Initialize the static mappings string in the environment
        )

        static_paths = self.get_static_paths()

        for static_url, static_path_ in static_paths:
            static_path = str(static_path_)
            log(f"nginx will map {static_url} to {static_path}.", level=2)
            self.env["HOP3_INTERNAL_NGINX_STATIC_MAPPINGS"] += expand_vars(
                HOP3_INTERNAL_NGINX_STATIC_MAPPING,
                locals(),
            )

        if nginx_include_file := self.env.get("NGINX_INCLUDE_FILE"):
            tpl = Path(self.app_path, nginx_include_file).read_text()
        else:
            tpl = ""
        self.env["HOP3_INTERNAL_NGINX_CUSTOM_CLAUSES"] = expand_vars(tpl, self.env)
        self.env["HOP3_INTERNAL_NGINX_PORTMAP"] = ""

    def check_config(self) -> None:
        """Prevent broken config from breaking other deployments."""
        # FIXME: currently broken (should be run as root)
        return

        # try:
        #     subprocess.check_output(["/usr/sbin/nginx", "-t"])
        # except subprocess.CalledProcessError:
        #     echo(f"Error: broken nginx config - removing", fg="red")
        #     content = self.nginx_conf_path.read_text()
        #     echo(f"here is the broken config\n{content}")
        #     # self.nginx_conf_path.unlink()
        #     sys.exit(1)

    def _validate_nginx_config(self, client: LocalRootdClient) -> bool:
        """Validate nginx configuration before reload via hop3-rootd.

        Returns:
            True if config is valid.
            False if config is invalid.

        Caller is responsible for handling RootdUnavailableError (which
        propagates here on a closed/refused connection).
        """
        try:
            result = client.call("nginx.validate_config", {})
        except RootdOpError as e:
            log_diagnosis(
                Diagnosis(
                    component="Nginx",
                    action="validate configuration",
                    reason=f"hop3-rootd returned error: {e.message}",
                    hint="Check journalctl -u hop3-rootd for details.",
                )
            )
            return False

        if result.get("valid", False):
            return True

        errors = result.get("errors", [])
        log_diagnosis(
            Diagnosis(
                component="Nginx",
                action="validate configuration",
                reason="`nginx -t` reported errors via hop3-rootd",
                hint=(
                    f"Inspect the generated config at "
                    f"{self.nginx_conf_path} and re-run validation"
                ),
                troubleshooting=[
                    f"cat {self.nginx_conf_path}",
                    *errors,
                    (
                        "If the error mentions a missing include or "
                        "upstream, check that all apps referenced by the "
                        "proxy are still deployed."
                    ),
                ],
            )
        )
        return False

    def reload_proxy(self) -> None:
        """Reload nginx to apply configuration changes.

        Reloads via hop3-rootd, the privileged-operations daemon (ADR 041).
        The daemon is a hard dependency of the deploy path: if it is not
        reachable, or the reload op fails, the new routes cannot be
        published and the deploy is aborted with an actionable diagnosis —
        we do NOT silently continue against a stale nginx.

        The only non-fatal path is a generated config that fails `nginx -t`:
        the previously-running config stays live and the deploy stops so the
        operator can fix the error and redeploy.

        Skipped only in unit/integration tests (not E2E), which run without a
        live daemon.
        """
        # Skip reload in unit/integration tests, but NOT in E2E tests
        # E2E tests run in Docker containers and need nginx to actually reload
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
            "HOP3_E2E_TEST"
        ):
            return

        try:
            with LocalRootdClient() as client:
                if not self._validate_nginx_config(client):
                    abort_with_diagnosis(
                        Diagnosis(
                            component="Nginx",
                            action="reload proxy",
                            reason=(
                                "the generated nginx config failed validation "
                                "(see the validation diagnosis above)"
                            ),
                            hint=(
                                "The previously-running nginx config is still "
                                "live; fix the error and redeploy to publish "
                                "the new routes"
                            ),
                        )
                    )
                result = client.call("nginx.reload", {})
            method = result.get("method", "rootd")
            log(f"nginx reloaded via {method} (hop3-rootd)", level=2)
        except RootdUnavailableError as e:
            # rootd is required to apply proxy changes. Its absence is a
            # deploy-blocker (see RootdUnavailableError) — fail loudly rather
            # than report success against a stale nginx the operator must
            # reload by hand.
            abort_with_diagnosis(
                Diagnosis(
                    component="Nginx",
                    action="reload proxy",
                    reason=f"hop3-rootd is not reachable: {e}",
                    hint=(
                        "The platform requires the hop3-rootd daemon to apply "
                        "proxy changes. Start it, then redeploy."
                    ),
                    troubleshooting=[
                        "systemctl status hop3-rootd   # systemd hosts",
                        "supervisorctl status hop3-rootd   # containers",
                        "ls -l /run/hop3-rootd/socket",
                    ],
                )
            )
        except RootdOpError as e:
            abort_with_diagnosis(
                Diagnosis(
                    component="Nginx",
                    action="reload proxy",
                    reason=(f"hop3-rootd returned an error: {e.message.strip()}"),
                    hint=(
                        "nginx was not reloaded, so the new routes are not "
                        "live. Inspect the daemon logs, fix the cause, and "
                        "redeploy."
                    ),
                    troubleshooting=[
                        "journalctl -u hop3-rootd -n 50   # systemd hosts",
                        "supervisorctl tail hop3-rootd stderr   # containers",
                        "systemctl status nginx",
                    ],
                )
            )

    def setup_cache(self) -> None:
        """Configure Nginx caching for the application.

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
                log(
                    f"nginx will cache /({cache_prefixes}) prefixes up to"
                    f" {cache_time_expiry} or {cache_size} of disk space, with the"
                    " following timings:",
                    level=2,
                )
                log(f"nginx will cache content for {cache_time_content}.", level=2)
                log(f"nginx will cache redirects for {cache_time_redirects}.", level=2)
                log(f"nginx will cache everything else for {cache_time_any}.", level=2)
                log(
                    "nginx will send caching headers asking for"
                    f" {cache_time_control} seconds of public caching.",
                    level=2,
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
                log(
                    f"Error {e} in cache path spec: should be /prefix1:[,/prefix2],"
                    " ignoring.",
                )
                self.env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"] = ""

    def _get_cache_param(self, key: str, name: str, default: int, suffix: str) -> str:
        """Generate a cache parameter string by retrieving an integer value
        from the environment.

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
            log(f"Invalid {name}, defaulting to {default}{suffix}", level=2)
            return str(default) + suffix
