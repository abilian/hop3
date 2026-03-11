# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import re
import shutil
import subprocess
from textwrap import dedent
from typing import TYPE_CHECKING

from attrs import frozen

from hop3.config import ACME_EMAIL, ACME_ENGINE, HOP3_ROOT, NGINX_ROOT
from hop3.lib import log

if TYPE_CHECKING:
    from pathlib import Path

KEY_STORE = HOP3_ROOT / "certificates"
KEY_STORE.mkdir(parents=True, exist_ok=True)

RE_DOMAIN_VALIDATOR = re.compile(
    r"^((?!-))(xn--)?[a-z0-9][a-z0-9-_]{0,61}[a-z0-9]{0,1}\.(xn--)?([a-z0-9\-]{1,61}|[a-z0-9-]{1,30}\.[a-z]{2,})$"
)


class CertificatesManager:
    """Stateless service class for managing SSL certificates.

    This service is now managed by Dishka dependency injection framework.
    It is registered in APP scope, meaning a single instance is created
    and reused throughout the application lifetime.
    """

    def get_certificate(self, domain_name: str) -> Certificate:
        # if not RE_DOMAIN_VALIDATOR.match(domain_name):
        #     msg = f"Invalid domain name: {domain_name}"
        #     raise ValueError(msg)

        certificate = Certificate(domain_name=domain_name)
        if not certificate.crt_file.exists():
            certificate.generate()
        return certificate


@frozen
class Certificate:
    domain_name: str

    @property
    def key_file(self) -> Path:
        return KEY_STORE / f"{self.domain_name}.key"

    @property
    def crt_file(self) -> Path:
        return KEY_STORE / f"{self.domain_name}.crt"

    def get_key(self):
        return self.key_file.read_text()

    def get_crt(self):
        return self.crt_file.read_text()

    def generate(self) -> None:
        match ACME_ENGINE:
            case "self-signed":
                self.generate_self_signed()
            case "certbot":
                self.generate_with_certbot()
            case _:
                msg = f"Unknown certificate generation method: {ACME_ENGINE}"
                raise ValueError(msg)

    def generate_self_signed(self) -> None:
        """Generate a self-signed SSL certificate for the specified domain.

        Uses the OpenSSL command-line tool to generate a self-signed
        certificate with a 4096-bit RSA key, valid for 365 days.
        """
        log("Generating self-signed certificate", level=2)
        cmd = (
            "openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 -subj"
            f' "/C=FR/ST=NA/L=Paris/O=Hop3/OU=Self-Signed/CN={self.domain_name}"'
            f" -keyout {self.key_file} -out {self.crt_file}"
        )
        shell(cmd)

    def generate_with_certbot(self):
        # Validate domain name before attempting certbot
        if not RE_DOMAIN_VALIDATOR.match(self.domain_name.lower()):
            msg = (
                f"Invalid domain name for certbot: '{self.domain_name}'. "
                "Certbot requires a valid FQDN (e.g., 'example.com'). "
                "Use ACME_ENGINE=self-signed for development or catch-all domains."
            )
            raise ValueError(msg)

        # Check if certbot is installed
        if not shutil.which("certbot"):
            log(
                "certbot not found, falling back to self-signed certificate. "
                "Install certbot for Let's Encrypt certificates, or set "
                "ACME_ENGINE=self-signed to suppress this warning.",
                level=1,
                fg="yellow",
            )
            self.generate_self_signed()
            return

        certbot_root = HOP3_ROOT / "certbot"
        live_cert_file = certbot_root / f"config/live/{self.domain_name}/fullchain.pem"
        live_key_file = certbot_root / f"config/live/{self.domain_name}/privkey.pem"

        if not live_cert_file.exists() or not live_key_file.exists():
            webroot = certbot_root / "webroot"

            webroot.mkdir(parents=True, exist_ok=True)

            nginx_webroot_conf = dedent(
                f"""
                server {{
                  listen      [::]:80;
                  listen      0.0.0.0:80;
                  server_name {self.domain_name};

                  location ^~ /.well-known/acme-challenge {{
                    allow all;
                    root {webroot};
                  }}
                }}
                """
            )

            (NGINX_ROOT / "__certbot_webroot.conf").write_text(nginx_webroot_conf)

            # Reload nginx so it picks up the webroot config for ACME challenge
            _reload_nginx()

            cmd = (
                f"certbot certonly --webroot -w {webroot} -d {self.domain_name} -n "
                f"--config-dir {certbot_root}/config "
                f"--work-dir {certbot_root}/work "
                f"--logs-dir {certbot_root}/logs "
                f"--agree-tos --email {ACME_EMAIL}"
            )

            try:
                shell(cmd)
            except subprocess.CalledProcessError as e:
                # Clean up temporary nginx config
                (NGINX_ROOT / "__certbot_webroot.conf").unlink(missing_ok=True)

                # Build detailed error message
                error_details = [
                    f"certbot failed for domain '{self.domain_name}' (exit code {e.returncode})"
                ]
                if e.stderr:
                    error_details.append(f"stderr: {e.stderr}")
                if e.stdout:
                    error_details.append(f"stdout: {e.stdout}")

                # Check certbot logs for more details
                certbot_log = certbot_root / "logs" / "letsencrypt.log"
                if certbot_log.exists():
                    try:
                        # Get last 20 lines of log
                        log_tail = certbot_log.read_text().strip().split("\n")[-20:]
                        error_details.append(
                            f"certbot log ({certbot_log}):\n" + "\n".join(log_tail)
                        )
                    except Exception:
                        pass

                error_msg = "\n".join(error_details)
                msg = (
                    f"Certificate generation failed:\n{error_msg}\n\n"
                    "Common causes:\n"
                    "  - Domain DNS not pointing to this server\n"
                    "  - Port 80 not accessible from the internet\n"
                    "  - Rate limit exceeded (check https://letsencrypt.org/docs/rate-limits/)\n\n"
                    "To use self-signed certificates instead, set ACME_ENGINE=self-signed"
                )
                raise RuntimeError(msg) from e

            (NGINX_ROOT / "__certbot_webroot.conf").unlink(missing_ok=True)

        cert = live_cert_file.read_text()
        self.crt_file.write_text(cert)

        key = live_key_file.read_text()
        self.key_file.write_text(key)


def _reload_nginx() -> None:
    """Reload nginx to apply configuration changes.

    Tries supervisorctl first (Docker/E2E), then systemctl (systemd).
    Raises RuntimeError if nginx cannot be reloaded.
    """
    # Skip reload in test environments
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    # Try supervisorctl restart (for Docker/E2E environments)
    try:
        subprocess.run(
            ["sudo", "-n", "supervisorctl", "restart", "nginx"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        log("nginx reloaded for ACME challenge", level=2)
        return
    except Exception:
        pass

    # Try systemctl reload (for systemd)
    try:
        subprocess.run(
            ["sudo", "-n", "systemctl", "reload", "nginx"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        log("nginx reloaded for ACME challenge", level=2)
        return
    except Exception:
        pass

    # If we can't reload nginx, the ACME challenge will fail
    msg = (
        "Cannot reload nginx to serve ACME challenge. "
        "Ensure sudo is configured for passwordless nginx reload."
    )
    raise RuntimeError(msg)


def shell(cmd):
    log(f"Running command: {cmd}", level=2)
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Re-raise with captured output available
        error = subprocess.CalledProcessError(result.returncode, cmd)
        error.stdout = result.stdout
        error.stderr = result.stderr
        raise error
