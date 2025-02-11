# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

from attr import frozen

from hop3.config import c
from hop3.util import log


@frozen
class CertificatesManager:
    app_name: str
    env: dict[str, str]

    @property
    def domains(self) -> list[str]:
        return self.env["NGINX_SERVER_NAME"].split()

    @property
    def domain(self) -> str:
        return self.domains[0]

    @property
    def key(self) -> Path:
        return c.NGINX_ROOT / f"{self.app_name}.key"

    @property
    def crt(self) -> Path:
        return c.NGINX_ROOT / f"{self.app_name}.crt"

    def setup_certificates(self) -> None:
        """Sets up certificates for the instance.

        Checks if the key file exists or if the certificate file is
        empty. If either condition is true, it proceeds to set up a
        self-signed certificate.
        """
        # Check if the key file does not exist or if the certificate file size is zero
        if not self.key.exists() or self.crt.stat().st_size == 0:
            self.setup_self_signed()  # Set up a self-signed certificate if conditions are met

    def setup_self_signed(self) -> None:
        """Generate a self-signed SSL certificate for the specified domain.

        Uses the OpenSSL command-line tool to generate a self-signed
        certificate with a 4096-bit RSA key, valid for 365 days, and
        saves the certificate and key to the specified file paths.
        """
        log("Generating self-signed certificate", level=2)
        # Construct the OpenSSL command for generating a self-signed certificate
        cmd = (
            "openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 -subj"
            f' "/C=FR/ST=NA/L=Paris/O=Hop3/OU=Self-Signed/CN={self.domain}" -keyout'
            f" {self.key} -out {self.crt}"
        )
        subprocess.run(cmd, shell=True, check=True)

    def setup_acme(self) -> None:
        """Sets up the ACME environment for Let's Encrypt certificate issuance
        and installation.

        Checks for existing certificate files and issues new ones using
        acme.sh if not found. It also creates symbolic links required
        for ACME challenges and certificate management.
        """
        key_file = c.NGINX_ROOT / f"{self.app_name}.key"
        crt_file = c.NGINX_ROOT / f"{self.app_name}.crt"

        issue_file = Path(c.ACME_ROOT, self.domain, "issued-" + "-".join(self.domains))

        acme = c.ACME_ROOT
        www = c.ACME_WWW
        root_ca = c.ACME_ROOT_CA

        # if this is the first run there will be no nginx conf yet
        # create a basic conf stub just to serve the acme auth
        # FIXME
        # if not Path(nginx_conf).exists():
        #     echo("-----> writing temporary nginx conf")
        #     buffer = expand_vars(NGINX_ACME_FIRSTRUN_TEMPLATE, self.env)
        #     Path(nginx_conf).write_text(buffer)

        # Check if the key and issue files exist to determine if a certificate is already installed
        if key_file.exists() and issue_file.exists():
            log("letsencrypt certificate already installed", level=3)
            return

        log("getting letsencrypt certificate", level=3)
        certlist = " ".join([f"-d {d}" for d in self.domains])
        # Run the acme.sh script to issue a certificate
        subprocess.call(
            f"{acme:s}/acme.sh --issue {certlist:s} -w {www:s} --server {root_ca:s}",
            shell=True,
        )
        # Run the acme.sh script to install the certificate
        subprocess.call(
            f"{acme:s}/acme.sh --install-cert {certlist:s} --key-file"
            f" {key_file:s} --fullchain-file {crt_file:s}",
            shell=True,
        )
        # Create a symbolic link if the ACME_ROOT path exists but not the ACME_WWW path
        if (c.ACME_ROOT / self.domain).exists() and not (
            c.ACME_WWW / self.app_name
        ).exists():
            os.symlink(c.ACME_ROOT / self.domain, c.ACME_WWW / self.app_name)

        with contextlib.suppress(Exception):
            os.symlink("/dev/null", issue_file)
