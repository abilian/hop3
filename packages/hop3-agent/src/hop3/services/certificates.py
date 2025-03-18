# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import subprocess
from pathlib import Path

from attrs import frozen
from wireup import service

from hop3.util import log

# TEMPORARY
# ROOT = Path("/home/hop3")
ROOT = Path("/tmp/hop3")
KEY_STORE = ROOT / "certificates"
METHOD = "self-signed"

KEY_STORE.mkdir(parents=True, exist_ok=True)


@service
class CertificatesManager:
    """Stateless service class for managing SSL certificates."""

    def get_certificate(self, domain_name: str) -> Certificate:
        certificate = Certificate(domain_name=domain_name)
        certificate.generate()
        return certificate


@frozen
class Certificate:
    domain_name: str

    def get_key(self):
        return self.key_file.read_text()

    def get_crt(self):
        return self.crt_file.read_text()

    @property
    def key_file(self) -> Path:
        return KEY_STORE / f"{self.domain_name}.key"

    @property
    def crt_file(self) -> Path:
        return KEY_STORE / f"{self.domain_name}.crt"

    def generate(self) -> None:
        match METHOD:
            case "self-signed":
                self.generate_self_signed()
            # case "acme":
            #     self.generate_acme()
            case _:
                msg = f"Unknown certificate generation method: {METHOD}"
                raise ValueError(msg)

    def generate_self_signed(self) -> None:
        """Generate a self-signed SSL certificate for the specified domain.

        Uses the OpenSSL command-line tool to generate a self-signed
        certificate with a 4096-bit RSA key, valid for 365 days, and
        saves the certificate and key to the specified file paths.
        """
        log("Generating self-signed certificate", level=2)
        cmd = (
            "openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 -subj"
            f' "/C=FR/ST=NA/L=Paris/O=Hop3/OU=Self-Signed/CN={self.domain_name}"'
            f" -keyout {self.key_file} -out {self.crt_file}"
        )
        subprocess.run(cmd, shell=True, check=True)

    # FIXME
    #
    # def generate_acme(self) -> None:
    #     """Sets up the ACME environment for Let's Encrypt certificate issuance
    #     and installation.
    #
    #     Checks for existing certificate files and issues new ones using
    #     acme.sh if not found. It also creates symbolic links required
    #     for ACME challenges and certificate management.
    #     """
    #     issue_file = Path(c.ACME_ROOT, self.domain_name, "issued-{self.}" + "-".join(self.domains))
    #
    #     acme = c.ACME_ROOT
    #     www = c.ACME_WWW
    #     root_ca = c.ACME_ROOT_CA
    #
    #     # if this is the first run there will be no nginx conf yet
    #     # create a basic conf stub just to serve the acme auth
    #     # FIXME
    #     # if not Path(nginx_conf).exists():
    #     #     echo("-----> writing temporary nginx conf")
    #     #     buffer = expand_vars(NGINX_ACME_FIRSTRUN_TEMPLATE, self.env)
    #     #     Path(nginx_conf).write_text(buffer)
    #
    #     # Check if the key and issue files exist to determine if a certificate is already installed
    #     if key_file.exists() and issue_file.exists():
    #         log("letsencrypt certificate already installed", level=3)
    #         return
    #
    #     log("getting letsencrypt certificate", level=3)
    #     certlist = " ".join([f"-d {d}" for d in self.domains])
    #     # Run the acme.sh script to issue a certificate
    #     subprocess.call(
    #         f"{acme:s}/acme.sh --issue {certlist:s} -w {www:s} --server {root_ca:s}",
    #         shell=True,
    #     )
    #     # Run the acme.sh script to install the certificate
    #     subprocess.call(
    #         f"{acme:s}/acme.sh --install-cert {certlist:s} --key-file"
    #         f" {key_file:s} --fullchain-file {crt_file:s}",
    #         shell=True,
    #     )
    #     # Create a symbolic link if the ACME_ROOT path exists but not the ACME_WWW path
    #     if (c.ACME_ROOT / self.domain).exists() and not (
    #         c.ACME_WWW / self.app_name
    #     ).exists():
    #         os.symlink(c.ACME_ROOT / self.domain, c.ACME_WWW / self.app_name)
    #
    #     with contextlib.suppress(Exception):
    #         os.symlink("/dev/null", issue_file)
