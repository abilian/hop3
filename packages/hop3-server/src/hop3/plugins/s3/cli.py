# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for the S3 addon.

Most S3 addon operations are handled by the generic
``hop3 addons:*`` commands (which dispatch to the Addon protocol
implementation). This module only adds S3-specific convenience
commands.
"""

from __future__ import annotations

from hop3.lib import echo
from hop3.lib.decorators import command


@command
class S3Cmd:
    """Manage S3 addons."""

    name = "s3"


@command
class S3InfoCmd:
    """Show server-wide S3 backend info: hop s3:info."""

    name = "s3:info"

    def run(self) -> None:
        from .backend import get_default_backend  # noqa: PLC0415

        try:
            backend = get_default_backend()
        except (ValueError, NotImplementedError) as e:
            echo(f"S3 backend not available: {e}")
            return

        echo(f"Backend: {backend.name}")
        echo(f"Endpoint: {backend.endpoint}")

        try:
            buckets = backend.list_buckets()
            hop3_buckets = [b for b in buckets if b.startswith("hop3-")]
            echo(f"Managed buckets: {len(hop3_buckets)}")
            for b in hop3_buckets:
                echo(f"  - {b}")
        except Exception as e:
            echo(f"Could not list buckets: {e}")
