# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for field validators."""

from __future__ import annotations

import pytest
from hop3_rootd.validation import (
    PORT_RANGE_MAX_SIZE,
    PortSpec,
    ValidationError,
    validate_app_name,
    validate_description,
    validate_port,
    validate_port_range,
    validate_port_spec,
    validate_protocol,
    validate_source,
)

# --- validate_port --------------------------------------------------------


def test_port_accepts_normal_values():
    assert validate_port(80) == 80
    assert validate_port(8448) == 8448
    assert validate_port(65535) == 65535
    assert validate_port(1) == 1


def test_port_rejects_below_min():
    with pytest.raises(ValidationError) as e:
        validate_port(0)
    assert e.value.field == "port"
    assert "out of range" in e.value.message


def test_port_rejects_above_max():
    with pytest.raises(ValidationError):
        validate_port(65536)


def test_port_rejects_negative():
    with pytest.raises(ValidationError):
        validate_port(-1)


def test_port_rejects_string():
    with pytest.raises(ValidationError) as e:
        validate_port("8448")
    assert "must be an integer" in e.value.message


def test_port_rejects_float():
    with pytest.raises(ValidationError):
        validate_port(8448.0)


def test_port_rejects_bool():
    """bool is a subclass of int in Python; we explicitly reject."""
    with pytest.raises(ValidationError) as e:
        validate_port(True)
    assert "bool" in e.value.message


def test_port_rejects_none():
    with pytest.raises(ValidationError):
        validate_port(None)


# --- validate_port_range --------------------------------------------------


def test_port_range_accepts_valid():
    assert validate_port_range([8000, 9000]) == (8000, 9000)
    assert validate_port_range([1, 16384]) == (1, 16384)
    # tuples also accepted
    assert validate_port_range((49152, 65535)) == (49152, 65535)


def test_port_range_accepts_single_port_range():
    """[N, N] is a degenerate but valid range of size 1."""
    assert validate_port_range([8000, 8000]) == (8000, 8000)


def test_port_range_rejects_wrong_arity():
    with pytest.raises(ValidationError) as e:
        validate_port_range([8000])
    assert "exactly 2" in e.value.message
    with pytest.raises(ValidationError):
        validate_port_range([8000, 9000, 10000])
    with pytest.raises(ValidationError):
        validate_port_range([])


def test_port_range_rejects_non_list():
    with pytest.raises(ValidationError) as e:
        validate_port_range("8000-9000")
    assert e.value.field == "port_range"


def test_port_range_rejects_start_gt_end():
    with pytest.raises(ValidationError) as e:
        validate_port_range([9000, 8000])
    assert "must be <=" in e.value.message


def test_port_range_rejects_oversize():
    """ADR 040 caps range size at 16384 (denial-of-firewall protection)."""
    # 30000-65535 = 35536 ports — too big
    with pytest.raises(ValidationError) as e:
        validate_port_range([30000, 65535])
    assert "exceeds cap" in e.value.message
    assert str(PORT_RANGE_MAX_SIZE) in e.value.message


def test_port_range_accepts_at_cap():
    # Exactly 16384 ports: 1 to 16384
    assert validate_port_range([1, 16384]) == (1, 16384)


def test_port_range_rejects_one_above_cap():
    with pytest.raises(ValidationError):
        validate_port_range([1, 16385])


def test_port_range_rejects_invalid_start():
    with pytest.raises(ValidationError) as e:
        validate_port_range([0, 8000])
    assert e.value.field == "port_range"
    assert "start" in e.value.message


def test_port_range_rejects_invalid_end():
    with pytest.raises(ValidationError) as e:
        validate_port_range([8000, 70000])
    assert e.value.field == "port_range"
    assert "end" in e.value.message


# --- validate_protocol ----------------------------------------------------


def test_protocol_accepts_tcp_udp():
    assert validate_protocol("tcp") == "tcp"
    assert validate_protocol("udp") == "udp"


def test_protocol_rejects_uppercase():
    with pytest.raises(ValidationError):
        validate_protocol("TCP")


def test_protocol_rejects_other_protocols():
    """ICMP, ESP, GRE explicitly out of scope for v1."""
    for proto in ("icmp", "esp", "gre", "any", ""):
        with pytest.raises(ValidationError):
            validate_protocol(proto)


def test_protocol_rejects_non_string():
    with pytest.raises(ValidationError):
        validate_protocol(6)
    with pytest.raises(ValidationError):
        validate_protocol(None)


# --- validate_source ------------------------------------------------------


def test_source_any():
    assert validate_source("any") == "any"


def test_source_ipv4_cidr():
    assert validate_source("10.0.0.0/8") == "10.0.0.0/8"
    assert validate_source("192.168.1.0/24") == "192.168.1.0/24"


def test_source_canonicalises_cidr():
    """Non-network-address host bits are zeroed."""
    assert validate_source("10.0.0.5/24") == "10.0.0.0/24"
    assert validate_source("192.168.1.42/16") == "192.168.0.0/16"


def test_source_single_host_cidr():
    assert validate_source("192.168.1.42/32") == "192.168.1.42/32"


def test_source_bare_host_treated_as_32():
    assert validate_source("192.168.1.42") == "192.168.1.42/32"


def test_source_rejects_ipv6():
    """v1 IPv4 only — IPv6 source filtering is a v2 feature."""
    with pytest.raises(ValidationError) as e:
        validate_source("fe80::/10")
    assert "IPv6" in e.value.message
    assert "v1" in e.value.message
    with pytest.raises(ValidationError):
        validate_source("::1/128")


def test_source_rejects_invalid_cidr():
    with pytest.raises(ValidationError):
        validate_source("not a cidr")
    with pytest.raises(ValidationError):
        validate_source("999.999.999.999/24")
    with pytest.raises(ValidationError):
        validate_source("10.0.0.0/33")


def test_source_rejects_non_string():
    with pytest.raises(ValidationError):
        validate_source(0)


def test_source_rejects_empty_string():
    with pytest.raises(ValidationError):
        validate_source("")


# --- validate_app_name ----------------------------------------------------


def test_app_name_accepts_normal():
    assert validate_app_name("matrix-1") == "matrix-1"
    assert validate_app_name("a-b-c-d") == "a-b-c-d"
    # Aligned with hop3-server's APP_NAME_RE — uppercase, digits, underscores,
    # mixed case all accepted.
    assert validate_app_name("MyApp") == "MyApp"
    assert validate_app_name("user_service_v2") == "user_service_v2"
    assert validate_app_name("110-flask-gunicorn-poetry") == "110-flask-gunicorn-poetry"


def test_app_name_accepts_max_length():
    name = "a" + "b" * 61 + "c"  # 63 chars total, alphanumeric edges
    assert validate_app_name(name) == name


def test_app_name_rejects_too_long():
    with pytest.raises(ValidationError):
        validate_app_name("a" + "b" * 63)  # 64 chars


def test_app_name_rejects_too_short():
    """Minimum length is 3 — must have a first, middle, and last char."""
    with pytest.raises(ValidationError):
        validate_app_name("a")
    with pytest.raises(ValidationError):
        validate_app_name("ab")


def test_app_name_rejects_starting_hyphen():
    with pytest.raises(ValidationError):
        validate_app_name("-matrix")


def test_app_name_rejects_trailing_hyphen_or_underscore():
    with pytest.raises(ValidationError):
        validate_app_name("matrix-")
    with pytest.raises(ValidationError):
        validate_app_name("matrix_")


def test_app_name_rejects_dot():
    with pytest.raises(ValidationError):
        validate_app_name("matrix.1")


def test_app_name_rejects_empty():
    with pytest.raises(ValidationError):
        validate_app_name("")


def test_app_name_rejects_non_string():
    with pytest.raises(ValidationError):
        validate_app_name(None)
    with pytest.raises(ValidationError):
        validate_app_name(42)


# --- validate_description -------------------------------------------------


def test_description_optional():
    assert validate_description(None) is None


def test_description_normal():
    assert validate_description("matrix federation") == "matrix federation"


def test_description_max_length():
    s = "x" * 200
    assert validate_description(s) == s


def test_description_too_long():
    with pytest.raises(ValidationError) as e:
        validate_description("x" * 201)
    assert "exceeds max" in e.value.message


def test_description_rejects_control_chars():
    """Tab, newline, carriage return all rejected — descriptions are single-line."""
    for ch in ("\t", "\n", "\r", "\x00", "\x1f", "\x7f"):
        with pytest.raises(ValidationError) as e:
            validate_description(f"hello{ch}world")
        assert "control character" in e.value.message


def test_description_accepts_unicode():
    """Non-control unicode is fine."""
    assert validate_description("matrix fédération 🎉") == "matrix fédération 🎉"


def test_description_rejects_non_string():
    with pytest.raises(ValidationError):
        validate_description(42)


# --- validate_port_spec (top-level) ---------------------------------------


def test_port_spec_with_single_port():
    spec = validate_port_spec({
        "port": 8448,
        "protocol": "tcp",
        "source": "any",
        "app_name": "matrix",
        "description": "fed",
    })
    assert isinstance(spec, PortSpec)
    assert spec.port == 8448
    assert spec.port_range is None
    assert spec.protocol == "tcp"
    assert spec.source == "any"
    assert spec.app_name == "matrix"
    assert spec.description == "fed"


def test_port_spec_with_port_range():
    spec = validate_port_spec({
        "port_range": [49152, 65535],
        "protocol": "udp",
        "source": "any",
        "app_name": "matrix-turn",
    })
    assert spec.port is None
    assert spec.port_range == (49152, 65535)
    assert spec.description is None


def test_port_spec_rejects_both_port_and_port_range():
    with pytest.raises(ValidationError) as e:
        validate_port_spec({
            "port": 80,
            "port_range": [8000, 9000],
            "protocol": "tcp",
            "source": "any",
            "app_name": "myapp",
        })
    assert "mutually exclusive" in e.value.message


def test_port_spec_rejects_neither_port_nor_port_range():
    with pytest.raises(ValidationError) as e:
        validate_port_spec({
            "protocol": "tcp",
            "source": "any",
            "app_name": "myapp",
        })
    assert "exactly one" in e.value.message


def test_port_spec_defaults_source_to_any():
    """`source` is optional; defaults to 'any' if absent."""
    spec = validate_port_spec({
        "port": 80,
        "protocol": "tcp",
        "app_name": "web",
    })
    assert spec.source == "any"


def test_port_spec_propagates_field_errors():
    """When an inner validator fails, the field name and message bubble up."""
    with pytest.raises(ValidationError) as e:
        validate_port_spec({
            "port": 99999,  # out of range
            "protocol": "tcp",
            "source": "any",
            "app_name": "web",
        })
    assert e.value.field == "port"
    assert "out of range" in e.value.message


def test_port_spec_rejects_missing_app_name():
    with pytest.raises(ValidationError) as e:
        validate_port_spec({
            "port": 80,
            "protocol": "tcp",
            "source": "any",
        })
    assert e.value.field == "app_name"


def test_port_spec_normalises_cidr_in_source():
    spec = validate_port_spec({
        "port": 5432,
        "protocol": "tcp",
        "source": "10.0.0.5/24",  # non-canonical form
        "app_name": "pgdb",
    })
    assert spec.source == "10.0.0.0/24"
