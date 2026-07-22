# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Subprocess entry point that runs ``lewaf-proxy`` via the YAML-config path.

Why this exists instead of the stock ``lewaf-proxy`` CLI: that CLI's
``--rules-file`` reads the file line-by-line into a flat rule list parsed by
``lewaf.integration``'s strict parser, which silently skips ``Include`` and
rejects ``SecDefaultAction`` — so it cannot load the OWASP CRS. The
``waf_config_file`` (YAML ``rule_files:``) path uses the full ``SecLangParser``
(Include + directives + multi-line rules), which is what the CRS needs.

``lewaf`` and ``uvicorn`` are imported lazily inside :func:`main`, never at
module top level: ``scan_package('hop3.plugins')`` imports this module on every
server start, but the optional ``lewaf`` extra (Python 3.12+) may be absent — a
top-level import would crash startup on non-WAF / 3.11 installs. Remove this shim
if ``lewaf-proxy`` grows a ``--config`` flag upstream.
"""

from __future__ import annotations

import argparse
import logging


def main() -> None:
    import uvicorn  # ruff:ignore[import-outside-top-level] — lazy: optional `waf` extra, subprocess-only
    from lewaf.proxy.server import (
        create_proxy_app,
    )

    parser = argparse.ArgumentParser(description="Hop3 LeWAF proxy launcher")
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--config", required=True, help="YAML waf config (rule_files)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--trusted-proxy-count", type=int, default=1)
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()

    # Quiet LeWAF's per-rule-match INFO logging: it emits hundreds of lines per
    # request (every CRS rule evaluated), which is heavy and floods stdout. The
    # structured audit trail (the ban scorer's input) is a separate stream.
    logging.getLogger("lewaf").setLevel(logging.WARNING)

    app = create_proxy_app(
        upstream_url=args.upstream,
        waf_config_file=args.config,
        trusted_proxy_count=args.trusted_proxy_count,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
