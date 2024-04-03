from __future__ import annotations

from hop3.util.console import log

__all__ = ["found_app"]


def found_app(kind) -> None:
    log(f"{kind} app detected.", level=5, fg="green")
