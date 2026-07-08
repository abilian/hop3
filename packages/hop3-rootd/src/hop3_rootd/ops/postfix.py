# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""postfix ops: configure the loopback email relay (ADR 054).

``postfix.configure`` writes the null-client ``main.cf`` + SASL map for the
active email backend and reloads Postfix. hop3-server calls it when an operator
selects the email backend (``hop3 server email backend relay``). Stateless: the
config lives on disk in ``/etc/postfix`` and survives a rootd restart, so there
is no state row to reconcile.

Every arg is re-validated at the kernel boundary (defense in depth); the SASL
password is never echoed back or logged.
"""

from __future__ import annotations

from typing import Any

from hop3_rootd import dkim, postfix as pf
from hop3_rootd.ops._base import OpContext, register
from hop3_rootd.protocol import Request
from hop3_rootd.validation import (
    ValidationError,
    validate_dkim_selector,
    validate_from_domain,
    validate_ipv4,
    validate_port,
    validate_relay_host,
    validate_sasl_value,
    validate_submission_port,
)

_CATCH_DEFAULT_HOST = "127.0.0.1"
_CATCH_DEFAULT_PORT = 1025  # Mailpit's default SMTP port
_DIRECT_DEFAULT_SELECTOR = "hop3"


@register("postfix.configure")
def configure(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Configure the loopback Postfix relay for the active backend.

    ``mode=relay`` (default) authenticates over TLS to a provider submission
    endpoint; ``mode=catch`` relays plaintext to a local dev sink (Mailpit);
    ``mode=direct`` delivers to recipients' MX itself, DKIM-signed.
    """
    mode = req.args.get("mode", "relay")
    if mode == "catch":
        return _configure_catch(req, ctx)
    if mode == "relay":
        return _configure_relay(req, ctx)
    if mode == "direct":
        return _configure_direct(req, ctx)
    raise ValidationError(
        "mode", f"must be 'relay', 'catch', or 'direct' (got {mode!r})"
    )


def _configure_direct(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Deliver to MX ourselves, signing with DKIM. Returns the DNS records to
    publish (SPF/DKIM/DMARC/PTR) — never a fake 'ready'."""
    domain = validate_from_domain(req.args.get("from_domain"))
    selector = validate_dkim_selector(
        req.args.get("dkim_selector", _DIRECT_DEFAULT_SELECTOR)
    )
    server_ip = validate_ipv4(req.args.get("server_ip"))

    key = dkim.ensure_keypair(domain, selector, exec=ctx.exec)
    dkim.write_opendkim_config(domain, selector)
    dkim.reload_opendkim(ctx.exec)

    result = pf.configure_direct(milter=dkim.milter_address(), exec=ctx.exec)
    records = dkim.publishable_records(domain, selector, key["value"], server_ip)
    return {
        "mode": "direct",
        "from_domain": domain,
        "dkim_selector": selector,
        "records": records,
        **result,
    }


def _configure_relay(req: Request, ctx: OpContext) -> dict[str, Any]:
    relay_host = validate_relay_host(req.args.get("relay_host"))
    relay_port = validate_submission_port(req.args.get("relay_port"))
    sasl_user = validate_sasl_value(req.args.get("sasl_user"), "sasl_user")
    sasl_password = validate_sasl_value(req.args.get("sasl_password"), "sasl_password")

    result = pf.configure(
        relay_host,
        relay_port,
        sasl_user=sasl_user,
        sasl_password=sasl_password,
        exec=ctx.exec,
    )
    # result carries {relayhost, reloaded} — never the password.
    return {
        "mode": "relay",
        "relay_host": relay_host,
        "relay_port": relay_port,
        **result,
    }


def _configure_catch(req: Request, ctx: OpContext) -> dict[str, Any]:
    catch_host = validate_relay_host(req.args.get("catch_host", _CATCH_DEFAULT_HOST))
    catch_port = validate_port(req.args.get("catch_port", _CATCH_DEFAULT_PORT))

    result = pf.configure(catch_host, catch_port, use_tls=False, exec=ctx.exec)
    return {
        "mode": "catch",
        "catch_host": catch_host,
        "catch_port": catch_port,
        **result,
    }
