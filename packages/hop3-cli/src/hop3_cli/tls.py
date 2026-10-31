# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""How the CLI verifies a server's certificate, wherever it talks to one."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from hop3_cli.config import Config


def resolve_ssl_verification(api_url: str, config: Config) -> bool | str:
    """
    The ``verify`` value for ``requests`` given the connection URL + config.

    Shared by the RPC client AND the SSE streaming path so both honor a pinned
    ``ssl_cert`` (chain-verify against it) and parse a string ``verify_ssl``
    ("false"/"0"/"no") identically. A non-HTTPS URL needs no verification.

    The streaming path used to hand-roll ``config.get("verify_ssl", True)``,
    which ignored a pinned ``ssl_cert`` (so the stream failed while ``/rpc``
    succeeded, reporting failure on a running deploy) and passed a *string*
    ``"false"`` straight to ``requests`` (read as a CA-bundle path → opaque
    OSError). Routing both through this one resolver closes that (audit
    2026-06 B1).
    """
    if urlparse(api_url).scheme != "https":
        return False

    ssl_cert_value = config.get("ssl_cert", None)
    if ssl_cert_value:
        # Pinned cert: verify the chain against it (hostname/SAN included).
        return str(ssl_cert_value)

    return not _verify_ssl_disabled(config.get("verify_ssl", None))


# audit M2: we do NOT call urllib3.disable_warnings() anywhere. When TLS
# verification is disabled (verify_ssl=false on an https URL), urllib3's
# InsecureRequestWarning is the operator's only signal that traffic —
# including the bearer token — is interceptable. Suppressing it globally hid a
# silent-MITM foot-gun. Left unsuppressed so the warning surfaces.


def _verify_ssl_disabled(verify_ssl_config: object) -> bool:
    """Whether ``verify_ssl`` is explicitly disabled (handles str + bool)."""
    if verify_ssl_config is None:
        return False
    if isinstance(verify_ssl_config, str):
        return verify_ssl_config.lower() in {"false", "0", "no"}
    return not bool(verify_ssl_config)
