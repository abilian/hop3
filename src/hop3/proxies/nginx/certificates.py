# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

from attr import frozen
from click import secho as echo

from hop3.system.constants import ACME_ROOT, ACME_ROOT_CA, ACME_WWW, NGINX_ROOT

# from hop3.util.templating import expand_vars

# from .templates import NGINX_ACME_FIRSTRUN_TEMPLATE


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
        return Path(NGINX_ROOT, f"{self.app_name}.key")

    @property
    def crt(self) -> Path:
        return Path(NGINX_ROOT, f"{self.app_name}.crt")

    def setup_certificates(self) -> None:
        if not self.key.exists() or self.crt.stat().st_size == 0:
            self.setup_self_signed()

    def setup_self_signed(self) -> None:
        echo("-----> generating self-signed certificate")
        cmd = (
            "openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 -subj"
            f' "/C=FR/ST=NA/L=Paris/O=Hop3/OU=Self-Signed/CN={self.domain}" -keyout'
            f" {self.key} -out {self.crt}"
        )
        subprocess.call(cmd, shell=True)

    def setup_acme(self) -> None:
        key_file, crt_file = (
            os.path.join(NGINX_ROOT, f"{self.app_name}.{x}") for x in ["key", "crt"]
        )
        issue_file = os.path.join(
            ACME_ROOT, self.domain, "issued-" + "-".join(self.domains)
        )

        acme = ACME_ROOT
        www = ACME_WWW
        root_ca = ACME_ROOT_CA

        # if this is the first run there will be no nginx conf yet
        # create a basic conf stub just to serve the acme auth
        # FIXME
        # if not Path(nginx_conf).exists():
        #     echo("-----> writing temporary nginx conf")
        #     buffer = expand_vars(NGINX_ACME_FIRSTRUN_TEMPLATE, self.env)
        #     Path(nginx_conf).write_text(buffer)

        if Path(key_file).exists() and Path(issue_file).exists():
            echo("-----> letsencrypt certificate already installed")
            return

        echo("-----> getting letsencrypt certificate")
        certlist = " ".join([f"-d {d}" for d in self.domains])
        subprocess.call(
            f"{acme:s}/acme.sh --issue {certlist:s} -w {www:s} --server {root_ca:s}",
            shell=True,
        )
        subprocess.call(
            f"{acme:s}/acme.sh --install-cert {certlist:s} --key-file"
            f" {key_file:s} --fullchain-file {crt_file:s}",
            shell=True,
        )
        if (
            Path(ACME_ROOT, self.domain).exists()
            and not Path(ACME_WWW, self.app_name).exists()
        ):
            os.symlink(
                os.path.join(ACME_ROOT, self.domain),
                os.path.join(ACME_WWW, self.app_name),
            )

        with contextlib.suppress(Exception):
            os.symlink("/dev/null", issue_file)
