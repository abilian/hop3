# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: EM101

"""Field validators for hop3-rootd request args.

Each `validate_*` function takes a raw value (from a deserialised JSON
request) and returns a normalised, typed value, or raises ValidationError.

Used by the ops layer (defense in depth — hop3-server validates upstream
via Hop3TomlSchema, but rootd re-checks every field on the wire).

See ADR 041 §4 for the schema.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Final, Literal

# --- Constants -------------------------------------------------------------

PORT_MIN: Final[int] = 1
PORT_MAX: Final[int] = 65535
PORT_RANGE_MAX_SIZE: Final[int] = 16384  # ADR 040 cap: prevents million-rule explosion

ALLOWED_PROTOCOLS: Final[frozenset[str]] = frozenset({"tcp", "udp"})

# App-name regex: must accept anything `hop3.core.identifiers.APP_NAME_RE`
# accepts upstream (alphanumeric edges, hyphens / underscores in the middle,
# total length 3-63). Kept as a copy here because the kernel-boundary daemon
# can't import from hop3-server (no runtime deps); ADR 041 §"No external
# dependencies". The two regexes must stay in lockstep — see
# packages/hop3-rootd/tests/a_unit/test_validation.py for the parity test.
APP_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]$"
)

DESCRIPTION_MAX_LEN: Final[int] = 200


# --- Exceptions ------------------------------------------------------------


class ValidationError(Exception):
    """Raised by a validator when a field fails its check.

    `field` is the spec field name (e.g. "port"); `message` describes
    what was wrong. The dispatcher translates this into a protocol-level
    `validation_failed` error response.
    """

    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


# --- Typed result ----------------------------------------------------------


@dataclass(frozen=True)
class PortSpec:
    """Validated, normalised firewall request spec.

    Either `port` or `port_range` is set, never both.
    `source` is either the literal "any" or a canonical-form IPv4 CIDR.
    """

    protocol: Literal["tcp", "udp"]
    app_name: str
    source: str
    port: int | None = None
    port_range: tuple[int, int] | None = None
    description: str | None = None


# --- Individual validators -------------------------------------------------


def validate_port(value: Any) -> int:
    """Validate an integer port number.

    Rejects bools (subclass of int in Python), non-ints, out-of-range.
    """
    # bool is a subclass of int — reject explicitly
    if isinstance(value, bool):
        raise ValidationError("port", "must be an integer (got bool)")
    if not isinstance(value, int):
        raise ValidationError(
            "port", f"must be an integer (got {type(value).__name__})"
        )
    if value < PORT_MIN or value > PORT_MAX:
        raise ValidationError("port", f"out of range [{PORT_MIN}, {PORT_MAX}]: {value}")
    return value


def validate_port_range(value: Any) -> tuple[int, int]:
    """Validate a [start, end] port range.

    - Exactly 2 elements, both ints, both in [1, 65535].
    - start <= end.
    - (end - start + 1) <= PORT_RANGE_MAX_SIZE per ADR 040.
    """
    if not isinstance(value, (list, tuple)):
        raise ValidationError(
            "port_range",
            f"must be a 2-element list (got {type(value).__name__})",
        )
    if len(value) != 2:
        raise ValidationError(
            "port_range", f"must have exactly 2 elements (got {len(value)})"
        )
    start, end = value
    # Reuse port validator for each element; rewrap errors to point at port_range.
    try:
        start = validate_port(start)
    except ValidationError as e:
        raise ValidationError("port_range", f"start: {e.message}") from None
    try:
        end = validate_port(end)
    except ValidationError as e:
        raise ValidationError("port_range", f"end: {e.message}") from None

    if start > end:
        raise ValidationError("port_range", f"start ({start}) must be <= end ({end})")
    size = end - start + 1
    if size > PORT_RANGE_MAX_SIZE:
        raise ValidationError(
            "port_range",
            f"range size {size} exceeds cap of {PORT_RANGE_MAX_SIZE}",
        )
    return start, end


def validate_protocol(value: Any) -> Literal["tcp", "udp"]:
    """Validate a protocol literal — must be lowercase 'tcp' or 'udp'."""
    if not isinstance(value, str):
        raise ValidationError(
            "protocol", f"must be a string (got {type(value).__name__})"
        )
    if value not in ALLOWED_PROTOCOLS:
        raise ValidationError(
            "protocol",
            f"must be one of {sorted(ALLOWED_PROTOCOLS)} (got {value!r})",
        )
    return value  # type: ignore[return-value]  # narrowed by the membership check


def validate_source(value: Any) -> str:
    """Validate a source CIDR or the literal 'any'.

    Rejects IPv6 in v1 with a specific message ("not supported in v1").
    Returns the normalised form: "any", or `str(ipaddress.IPv4Network(...))`.
    """
    if not isinstance(value, str):
        raise ValidationError(
            "source", f"must be a string (got {type(value).__name__})"
        )
    if value == "any":
        return "any"
    try:
        net = ipaddress.ip_network(value, strict=False)
    except (ValueError, TypeError) as e:
        raise ValidationError(
            "source", f"not a valid CIDR or 'any': {value!r} ({e})"
        ) from None
    if isinstance(net, ipaddress.IPv6Network):
        raise ValidationError(
            "source",
            f"IPv6 sources not supported in v1 (got {value!r})",
        )
    # Canonicalise (e.g. "10.0.0.5/24" → "10.0.0.0/24")
    return str(net)


def validate_app_name(value: Any) -> str:
    """Validate an app name. Lowercase ascii; starts alpha; length 1-63."""
    if not isinstance(value, str):
        raise ValidationError(
            "app_name", f"must be a string (got {type(value).__name__})"
        )
    if not APP_NAME_RE.match(value):
        raise ValidationError(
            "app_name",
            f"must match {APP_NAME_RE.pattern!r} (got {value!r})",
        )
    return value


def validate_description(value: Any) -> str | None:
    """Validate the optional description field.

    Returns None when value is None (field omitted). Otherwise returns the
    string. Rejects non-strings, over-length, and any control characters.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(
            "description", f"must be a string or null (got {type(value).__name__})"
        )
    if len(value) > DESCRIPTION_MAX_LEN:
        raise ValidationError(
            "description",
            f"length {len(value)} exceeds max {DESCRIPTION_MAX_LEN}",
        )
    # Reject control characters: \x00-\x1f, \x7f. Tab/newline included
    # — descriptions are single-line metadata, not freeform text.
    for ch in value:
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise ValidationError(
                "description",
                f"contains control character {ord(ch):#04x}",
            )
    return value


# --- Top-level: full PortSpec validation -----------------------------------


def validate_port_spec(args: dict[str, Any]) -> PortSpec:
    """Validate the full args dict for `firewall.add_rule`.

    - Exactly one of `port` / `port_range` must be set.
    - All other fields validated independently.
    - Returns a typed, normalised PortSpec.
    """
    has_port = "port" in args and args["port"] is not None
    has_range = "port_range" in args and args["port_range"] is not None

    if has_port and has_range:
        raise ValidationError(
            "port",
            "cannot set both 'port' and 'port_range' (they're mutually exclusive)",
        )
    if not has_port and not has_range:
        raise ValidationError(
            "port", "exactly one of 'port' or 'port_range' must be set"
        )

    port: int | None = None
    port_range: tuple[int, int] | None = None
    if has_port:
        port = validate_port(args["port"])
    else:
        port_range = validate_port_range(args["port_range"])

    protocol = validate_protocol(args.get("protocol"))
    source = validate_source(args.get("source", "any"))
    app_name = validate_app_name(args.get("app_name"))
    description = validate_description(args.get("description"))

    return PortSpec(
        protocol=protocol,
        app_name=app_name,
        source=source,
        port=port,
        port_range=port_range,
        description=description,
    )
