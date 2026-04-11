# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Structured diagnostic messages for deployment failures.

When something fails deep in the deployment pipeline, users get a
``[Component] can't [action]: [reason]. [Hint]`` message that names
the failing component, what it was trying to do, why it failed, and
what to do next — instead of a generic "failed" or opaque traceback.

Usage::

    from hop3.lib.diagnostics import Diagnosis, abort_with_diagnosis

    abort_with_diagnosis(
        Diagnosis(
            component="Docker builder",
            action="build image",
            reason="Dockerfile references missing FROM image 'python:3.99'",
            hint="Check the FROM directive in your Dockerfile",
            troubleshooting=[
                "Run `docker pull python:3.99` manually to confirm",
                "Consult https://hub.docker.com/_/python for available tags",
            ],
        )
    )

This produces a consistent, actionable error that the user actually
understands, and optionally raises :class:`hop3.lib.Abort`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NoReturn

from .console import log

__all__ = [
    "Diagnosis",
    "abort_with_diagnosis",
    "format_diagnosis",
    "log_diagnosis",
]


@dataclass(frozen=True)
class Diagnosis:
    """A structured diagnostic message.

    Attributes:
        component: The failing subsystem (e.g., "Docker builder",
            "Addon provisioning", "Nix builder"). Written in title
            case, no trailing punctuation.
        action: What the component was trying to do when it failed
            (e.g., "build image", "connect to PostgreSQL"). Written
            as an infinitive verb phrase.
        reason: Concrete, plain-language explanation of why it
            failed. One sentence, no jargon if possible.
        hint: A single concrete next step the user can take. One
            sentence, imperative mood.
        troubleshooting: Optional list of additional commands or
            links the user can try if the hint doesn't solve it.
    """

    component: str
    action: str
    reason: str
    hint: str = ""
    troubleshooting: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Enforce the shape early — these are user-facing messages
        # and a malformed Diagnosis produces worse UX than the
        # original opaque error.
        if not self.component:
            msg = "Diagnosis.component is required"
            raise ValueError(msg)
        if not self.action:
            msg = "Diagnosis.action is required"
            raise ValueError(msg)
        if not self.reason:
            msg = "Diagnosis.reason is required"
            raise ValueError(msg)


def format_diagnosis(diag: Diagnosis) -> str:
    """Format a diagnosis as a single string suitable for Abort().

    Follows the project's error message convention:
    ``[Component] can't [action]: [reason]. [Hint]``

    Troubleshooting items (if any) are appended on separate lines.
    """
    parts = [f"{diag.component} can't {diag.action}: {diag.reason}"]
    if diag.hint:
        # Ensure the hint reads as its own sentence
        hint = diag.hint.rstrip(".")
        parts[0] += f". {hint}."
    else:
        parts[0] += "."

    if diag.troubleshooting:
        parts.append("")
        parts.append("Troubleshooting:")
        parts.extend(f"  - {item}" for item in diag.troubleshooting)

    return "\n".join(parts)


def log_diagnosis(diag: Diagnosis, level: int = 0, fg: str = "red") -> None:
    """Write a diagnosis to the log in the format used by deployer.py.

    Useful when you want to print a structured diagnosis BEFORE
    raising a less-detailed Abort (so the user sees the diagnosis
    in the log stream), or when diagnosing non-fatal conditions.
    """
    log(f"Diagnosis: {diag.component} can't {diag.action}.", level=level, fg=fg)
    log(f"  Reason: {diag.reason}", level=level)
    if diag.hint:
        log(f"  Fix: {diag.hint}", level=level, fg="yellow")
    if diag.troubleshooting:
        log("  Troubleshooting:", level=level, fg="yellow")
        for item in diag.troubleshooting:
            log(f"    - {item}", level=level)


def abort_with_diagnosis(diag: Diagnosis) -> NoReturn:
    """Raise :class:`hop3.lib.Abort` with a formatted diagnosis.

    The exception message is the formatted diagnosis, so the caller
    gets a usable error whether they log it, print it, or send it
    back over the wire.
    """
    # Local import to avoid circular dependency: lib/diagnostics.py
    # is imported by various modules that lib/__init__.py also pulls in.
    from .console import Abort  # noqa: PLC0415

    raise Abort(format_diagnosis(diag))
