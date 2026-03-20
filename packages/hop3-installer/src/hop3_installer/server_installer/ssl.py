# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""SSL certificate management."""

from __future__ import annotations

from pathlib import Path

from hop3_installer.common import (
    Spinner,
    print_detail,
    print_info,
    print_success,
    run_cmd,
)
from hop3_installer.constants import (
    SSL_CERT_VALIDITY_DAYS,
    SYSTEM_SSL_CERT,
    SYSTEM_SSL_DIR,
    SYSTEM_SSL_KEY,
)


def setup_ssl_selfsigned() -> None:
    """Generate a self-signed SSL certificate."""
    if SYSTEM_SSL_CERT.exists() and SYSTEM_SSL_KEY.exists():
        print_info("SSL certificates already exist")
        return

    # Create SSL directory
    SYSTEM_SSL_DIR.mkdir(parents=True, exist_ok=True)

    with Spinner("Generating self-signed SSL certificate..."):
        run_cmd([
            "openssl",
            "req",
            "-x509",
            "-nodes",
            "-days",
            str(SSL_CERT_VALIDITY_DAYS),
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(SYSTEM_SSL_KEY),
            "-out",
            str(SYSTEM_SSL_CERT),
            "-subj",
            "/CN=hop3-server/O=Hop3/C=US",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ])

    Path(SYSTEM_SSL_KEY).chmod(0o600)
    Path(SYSTEM_SSL_CERT).chmod(0o644)

    print_success("Self-signed SSL certificate generated")
    print_detail(f"Certificate: {SYSTEM_SSL_CERT}")
    print_detail(f"Private key: {SYSTEM_SSL_KEY}")
