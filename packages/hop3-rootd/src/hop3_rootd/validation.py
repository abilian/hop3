# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


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

# Addon-type token (e.g. "postgres", "mysql", "redis"): lowercase alphanumeric,
# starts with a letter, bounded. Used (with the addon name) to compose the
# systemd unit name `hop3-expose-<type>-<name>`, so it must never contain a
# path separator or systemd/shell metacharacter.
ADDON_TYPE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9]{1,31}$")

# cgroup limits (ADR 046 §3 / P2.2). Sanity bounds at the kernel boundary;
# the real policy (server-wide ceiling) lives in hop3-server's HopConfig.
MEMORY_MAX_BYTES_CAP: Final[int] = 2**50  # 1 PiB — rejects nonsensical values
PID_LIST_MAX_LEN: Final[int] = 4096  # an app shouldn't attach more PIDs at once
# cgroup v2 cpu.max is "<quota_us> <period_us>" (two positive integers).
_CPU_MAX_RE: Final[re.Pattern[str]] = re.compile(r"^[1-9]\d* [1-9]\d*$")

# Email relay host (ADR 054). A hostname token — no whitespace, brackets,
# colon, or slash — so it can't break the composed `[host]:port` relayhost key
# or inject a second sasl_passwd line.
RELAY_HOST_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$"
)
# Only submission ports are valid relay targets; port 25 is never one.
SUBMISSION_PORTS: Final[frozenset[int]] = frozenset({587, 465})


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


@dataclass(frozen=True)
class CgroupLimits:
    """Validated, kernel-form ``cgroup.set_limits`` args (ADR 046 §3 / P2.2).

    Values are already in cgroup-native form (bytes, ``"quota period"``,
    pid count); the server maps ``[limits]`` → these before the wire call.
    At least one dimension is non-None.
    """

    app_name: str
    memory_max: int | None = None
    cpu_max: str | None = None
    pids_max: int | None = None


# --- Individual validators -------------------------------------------------


def _require_int(value: Any, field: str, *, kind: str = "an integer") -> int:
    """Validate ``value`` is a real int (not a bool) and return it.

    bool is a subclass of int in Python, so ``isinstance(True, int)`` is True —
    a JSON ``true`` would otherwise sneak through as ``1``. Centralised so the
    bool-rejection can't drift across the integer validators.
    """
    if isinstance(value, bool):
        raise ValidationError(field, "must be an integer (got bool)")
    if not isinstance(value, int):
        raise ValidationError(field, f"must be {kind} (got {type(value).__name__})")
    return value


def validate_port(value: Any) -> int:
    """Validate an integer port number. Rejects bools, non-ints, out-of-range."""
    value = _require_int(value, "port")
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
    return "tcp" if value == "tcp" else "udp"


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


def validate_addon_type(value: Any) -> str:
    """Validate an addon type token ("postgres", "mysql", "redis", …).

    Lowercase, starts with a letter, alphanumeric, bounded. Half of the
    proxy unit name; the regex guarantees no path/metacharacter can slip in.
    """
    if not isinstance(value, str):
        raise ValidationError(
            "addon_type", f"must be a string (got {type(value).__name__})"
        )
    if not ADDON_TYPE_RE.match(value):
        raise ValidationError(
            "addon_type", f"must match {ADDON_TYPE_RE.pattern!r} (got {value!r})"
        )
    return value


def validate_addon_name(value: Any) -> str:
    """Validate an addon instance name.

    Same shape as an app name (alphanumeric edges, hyphens/underscores in the
    middle, length 3-63) — the other half of the proxy unit name. Reuses
    ``APP_NAME_RE`` so the composed ``hop3-expose-<type>-<name>`` unit filename
    is always a safe identifier.
    """
    if not isinstance(value, str):
        raise ValidationError(
            "addon_name", f"must be a string (got {type(value).__name__})"
        )
    if not APP_NAME_RE.match(value):
        raise ValidationError(
            "addon_name", f"must match {APP_NAME_RE.pattern!r} (got {value!r})"
        )
    return value


def validate_memory_max(value: Any) -> int:
    """Validate a cgroup ``memory.max`` value in bytes.

    Rejects bools, non-ints, non-positive, and absurd values (a sanity cap so
    a compromised server can't request a nonsensical limit). The server maps
    ``[limits].memory`` ("512M") → bytes before calling.
    """
    value = _require_int(value, "memory_max", kind="an integer number of bytes")
    if value < 1:
        raise ValidationError("memory_max", f"must be >= 1 byte (got {value})")
    if value > MEMORY_MAX_BYTES_CAP:
        raise ValidationError(
            "memory_max", f"exceeds the sanity cap of {MEMORY_MAX_BYTES_CAP} bytes"
        )
    return value


def validate_cpu_max(value: Any) -> str:
    """Validate a cgroup v2 ``cpu.max`` value: ``"<quota_us> <period_us>"``.

    The server maps ``[limits].cpu`` (cores) → ``"150000 100000"`` before
    calling, so rootd only accepts the concrete two-integer form.
    """
    if not isinstance(value, str):
        raise ValidationError(
            "cpu_max", f"must be a string (got {type(value).__name__})"
        )
    if not _CPU_MAX_RE.match(value):
        raise ValidationError(
            "cpu_max",
            f"must be '<quota_us> <period_us>' (two positive integers), got {value!r}",
        )
    return value


def validate_pids_max(value: Any) -> int:
    """Validate a cgroup ``pids.max`` value (max processes/threads)."""
    value = _require_int(value, "pids_max")
    if value < 1:
        raise ValidationError("pids_max", f"must be >= 1 (got {value})")
    return value


def validate_pid_list(value: Any) -> list[int]:
    """Validate a non-empty, bounded list of positive PIDs to attach."""
    if not isinstance(value, list):
        raise ValidationError(
            "pids", f"must be a list of integers (got {type(value).__name__})"
        )
    if not value:
        raise ValidationError("pids", "must not be empty")
    if len(value) > PID_LIST_MAX_LEN:
        raise ValidationError(
            "pids", f"too many pids ({len(value)} > cap {PID_LIST_MAX_LEN})"
        )
    out: list[int] = []
    for pid in value:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
            raise ValidationError(
                "pids", f"each pid must be a positive integer (got {pid!r})"
            )
        out.append(pid)
    return out


def validate_cgroup_limits(args: dict[str, Any]) -> CgroupLimits:
    """Validate ``cgroup.set_limits`` args. At least one dimension required.

    A ``set_limits`` with no dimension would create an uncapped leaf that
    *looks* enforced — reject it loudly rather than no-op.
    """
    app_name = validate_app_name(args.get("app_name"))

    memory_max = None
    if args.get("memory_max") is not None:
        memory_max = validate_memory_max(args["memory_max"])
    cpu_max = None
    if args.get("cpu_max") is not None:
        cpu_max = validate_cpu_max(args["cpu_max"])
    pids_max = None
    if args.get("pids_max") is not None:
        pids_max = validate_pids_max(args["pids_max"])

    if memory_max is None and cpu_max is None and pids_max is None:
        raise ValidationError(
            "memory_max",
            "at least one of memory_max / cpu_max / pids_max must be set",
        )

    return CgroupLimits(
        app_name=app_name,
        memory_max=memory_max,
        cpu_max=cpu_max,
        pids_max=pids_max,
    )


def validate_volume_target(value: Any) -> str:
    """Validate a volume target: a non-empty relative path with no traversal.

    Mirrors the upstream ``VolumeSection`` target check (defense in depth at the
    kernel boundary). The daemon builds the mountpoint from this under the app's
    src dir, so an absolute path or ``..`` must be rejected.
    """
    if not isinstance(value, str):
        raise ValidationError(
            "target", f"must be a string (got {type(value).__name__})"
        )
    if not value or value.startswith("/"):
        raise ValidationError(
            "target", f"must be a non-empty relative path (got {value!r})"
        )
    if ".." in value.split("/"):
        raise ValidationError(
            "target", f"must not contain '..' (no escaping the app tree): {value!r}"
        )
    return value


def validate_size_bytes(value: Any) -> int:
    """Validate a tmpfs size in bytes (positive, sanity-capped)."""
    value = _require_int(value, "size_bytes")
    if value < 1:
        raise ValidationError("size_bytes", f"must be >= 1 (got {value})")
    if value > MEMORY_MAX_BYTES_CAP:
        raise ValidationError(
            "size_bytes", f"exceeds the sanity cap of {MEMORY_MAX_BYTES_CAP} bytes"
        )
    return value


def validate_mount_mode(value: Any) -> str | None:
    """Validate an optional octal mode string (e.g. '0700'). None when omitted."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(
            "mode", f"must be a string or null (got {type(value).__name__})"
        )
    try:
        int(value, 8)
    except ValueError:
        raise ValidationError(
            "mode", f"must be an octal string, e.g. '0700' (got {value!r})"
        ) from None
    return value


def validate_bind_source(value: Any) -> str:
    """Validate a bind-mount source: an absolute host path with no traversal.

    Only shape is checked here; whether the path is *allowed* (operator
    allow-list) and *exists* is enforced in the mount helper, which reads the
    allow-list and the filesystem.
    """
    if not isinstance(value, str):
        raise ValidationError(
            "source", f"must be a string (got {type(value).__name__})"
        )
    if not value or not value.startswith("/"):
        raise ValidationError(
            "source", f"bind source must be an absolute host path (got {value!r})"
        )
    if ".." in value.split("/"):
        raise ValidationError("source", f"must not contain '..' (got {value!r})")
    return value


def validate_read_only(value: Any) -> bool:
    """Validate the optional read_only flag (default False)."""
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValidationError(
            "read_only", f"must be a boolean (got {type(value).__name__})"
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


# --- Email relay (ADR 054) -------------------------------------------------


def validate_submission_port(value: Any) -> int:
    """Validate an SMTP submission port — 587 (STARTTLS) or 465 (implicit TLS).

    Port 25 is never a submission target, so the null-client can never be
    pointed at an MX-facing port.
    """
    value = _require_int(value, "relay_port")
    if value not in SUBMISSION_PORTS:
        raise ValidationError(
            "relay_port",
            f"must be a submission port {sorted(SUBMISSION_PORTS)} (got {value})",
        )
    return value


def validate_relay_host(value: Any) -> str:
    """Validate the email relay hostname.

    A hostname token only — the regex forbids whitespace, brackets, colon and
    slash, so it can't break the composed ``[host]:port`` relayhost key.
    """
    if not isinstance(value, str):
        raise ValidationError(
            "relay_host", f"must be a string (got {type(value).__name__})"
        )
    if not RELAY_HOST_RE.match(value):
        raise ValidationError("relay_host", f"must be a hostname (got {value!r})")
    return value


def validate_sasl_value(value: Any, field: str) -> str:
    """Validate a SASL credential field (user or password) for ``sasl_passwd``.

    Non-empty, no control characters: a newline would inject an extra map line
    (the entry is ``[host]:port user:password``), so the control-char rejection
    is the security-critical check here. The value is never logged or returned.
    """
    if not isinstance(value, str):
        raise ValidationError(field, f"must be a string (got {type(value).__name__})")
    if not value:
        raise ValidationError(field, "must not be empty")
    for ch in value:
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise ValidationError(field, f"contains control character {ord(ch):#04x}")
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
