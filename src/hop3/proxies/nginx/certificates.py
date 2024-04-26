# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

from click import secho as echo

from hop3.system.constants import ACME_ROOT, ACME_ROOT_CA, ACME_WWW, NGINX_ROOT
from hop3.util.templating import expand_vars

from .templates import NGINX_ACME_FIRSTRUN_TEMPLATE


def setup_certificates(app_name: str, env) -> None:
    domains = env["NGINX_SERVER_NAME"].split()
    domain = domains[0]
    key, crt = (os.path.join(NGINX_ROOT, f"{app_name}.{x}") for x in ["key", "crt"])

    # if Path(ACME_ROOT, "acme.sh").exists():
    #     setup_acme(app_name, env, nginx_conf)

    # fall back to creating self-signed certificate if acme failed
    if not Path(key).exists() or Path(crt).stat().st_size == 0:
        setup_self_signed(domain, key, crt)


def setup_self_signed(domain, key, crt) -> None:
    echo("-----> generating self-signed certificate")
    subprocess.call(
        "openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 -subj"
        f' "/C=FR/ST=NA/L=Paris/O=Hop3/OU=Self-Signed/CN={domain:s}" -keyout'
        f" {key:s} -out {crt:s}",
        shell=True,
    )


def setup_acme(app_name: str, env, nginx_conf) -> None:
    domains = env["NGINX_SERVER_NAME"].split()
    domain = domains[0]

    key_file, crt_file = (
        os.path.join(NGINX_ROOT, f"{app_name}.{x}") for x in ["key", "crt"]
    )
    issue_file = os.path.join(ACME_ROOT, domain, "issued-" + "-".join(domains))

    acme = ACME_ROOT
    www = ACME_WWW
    root_ca = ACME_ROOT_CA

    # if this is the first run there will be no nginx conf yet
    # create a basic conf stub just to serve the acme auth
    if not Path(nginx_conf).exists():
        echo("-----> writing temporary nginx conf")
        buffer = expand_vars(NGINX_ACME_FIRSTRUN_TEMPLATE, env)
        Path(nginx_conf).write_text(buffer)

    if Path(key_file).exists() and Path(issue_file).exists():
        echo("-----> letsencrypt certificate already installed")
        return

    echo("-----> getting letsencrypt certificate")
    certlist = " ".join([f"-d {d}" for d in domains])
    subprocess.call(
        f"{acme:s}/acme.sh --issue {certlist:s} -w {www:s} --server {root_ca:s}",
        shell=True,
    )
    subprocess.call(
        f"{acme:s}/acme.sh --install-cert {certlist:s} --key-file"
        f" {key_file:s} --fullchain-file {crt_file:s}",
        shell=True,
    )
    if Path(ACME_ROOT, domain).exists() and not Path(ACME_WWW, app_name).exists():
        os.symlink(os.path.join(ACME_ROOT, domain), os.path.join(ACME_WWW, app_name))

    with contextlib.suppress(Exception):
        os.symlink("/dev/null", issue_file)
