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

from hop3_rootd import postfix as pf
from hop3_rootd.ops._base import OpContext, register
from hop3_rootd.protocol import Request
from hop3_rootd.validation import (
    validate_relay_host,
    validate_sasl_value,
    validate_submission_port,
)


@register("postfix.configure")
def configure(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Configure the loopback Postfix relay to point at the active backend."""
    relay_host = validate_relay_host(req.args.get("relay_host"))
    relay_port = validate_submission_port(req.args.get("relay_port"))
    sasl_user = validate_sasl_value(req.args.get("sasl_user"), "sasl_user")
    sasl_password = validate_sasl_value(req.args.get("sasl_password"), "sasl_password")

    result = pf.configure_relay(
        relay_host,
        relay_port,
        sasl_user,
        sasl_password,
        exec=ctx.exec,
    )
    # result carries {relayhost, reloaded} — never the password.
    return {"relay_host": relay_host, "relay_port": relay_port, **result}
