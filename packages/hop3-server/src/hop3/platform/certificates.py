# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

from attrs import frozen

from hop3.config import ACME_EMAIL, ACME_ENGINE, HOP3_ROOT, NGINX_ROOT
from hop3.lib import log

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
                log(
                    f"certbot failed (exit code {e.returncode}), "
                    "falling back to self-signed certificate.",
                    level=1,
                    fg="yellow",
                )
                (NGINX_ROOT / "__certbot_webroot.conf").unlink(missing_ok=True)
                self.generate_self_signed()
                return

            (NGINX_ROOT / "__certbot_webroot.conf").unlink(missing_ok=True)

        cert = live_cert_file.read_text()
        self.crt_file.write_text(cert)

        key = live_key_file.read_text()
        self.key_file.write_text(key)


def shell(cmd):
    print(f"Running command: {cmd}")
    subprocess.run(cmd, shell=True, check=True)
