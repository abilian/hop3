# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Duration formatting for the --narrate timing reporter (ADR 043 phase 3).

Ported from the standalone demo harness (demos/lib) so its per-run timing
narration survives the move of demos into the unified hop3-test catalog.
"""

from __future__ import annotations


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as a readable string.

    Examples: ``1.5s``, ``2m 3.0s``.
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"
