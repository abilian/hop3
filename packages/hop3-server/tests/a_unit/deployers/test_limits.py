# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the [limits] functional core (ADR 046 §3 / P2.2)."""

from __future__ import annotations

import pytest

from hop3.deployers.limits import (
    LimitsError,
    ResolvedLimits,
    cpu_to_cgroup_max,
    parse_memory_to_bytes,
    resolve_limits,
    to_cgroup_args,
)

# --- parse_memory_to_bytes ------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("512", 512),
        ("512K", 512 * 1024),
        ("512M", 512 * 1024**2),
        ("1G", 1024**3),
        ("1g", 1024**3),  # case-insensitive
        (" 256M ", 256 * 1024**2),  # trimmed
    ],
)
def test_parse_memory_to_bytes(text, expected):
    assert parse_memory_to_bytes(text) == expected


def test_parse_memory_rejects_garbage():
    with pytest.raises(LimitsError, match="invalid memory"):
        parse_memory_to_bytes("5 gigs")


# --- cpu_to_cgroup_max ----------------------------------------------------


@pytest.mark.parametrize(
    ("cpu", "expected"),
    [
        (1.5, "150000 100000"),
        (1, "100000 100000"),
        (0.5, "50000 100000"),
        (2, "200000 100000"),
    ],
)
def test_cpu_to_cgroup_max(cpu, expected):
    assert cpu_to_cgroup_max(cpu) == expected


# --- resolve_limits -------------------------------------------------------


def test_resolve_declared_only_no_server_policy():
    r = resolve_limits({"memory": "512M", "cpu": 1.5}, {}, {})
    assert r == ResolvedLimits(memory="512M", cpu=1.5, processes=None)


def test_resolve_default_fills_unset_dimension():
    # App declares only memory; cpu comes from the server default, processes stays unset.
    r = resolve_limits({"memory": "512M"}, {"cpu": 1.0, "processes": 256}, {})
    assert r == ResolvedLimits(memory="512M", cpu=1.0, processes=256)


def test_resolve_declared_overrides_default():
    r = resolve_limits({"memory": "1G"}, {"memory": "512M"}, {})
    assert r.memory == "1G"


def test_resolve_empty_is_empty():
    assert resolve_limits({}, {}, {}).is_empty()


def test_resolve_declared_over_ceiling_aborts():
    with pytest.raises(LimitsError, match=r"declared.*exceeds the server ceiling"):
        resolve_limits({"memory": "4G"}, {}, {"memory": "2G"})


def test_resolve_cpu_over_ceiling_aborts():
    with pytest.raises(LimitsError, match="exceeds the server ceiling"):
        resolve_limits({"cpu": 8.0}, {}, {"cpu": 4.0})


def test_resolve_default_over_ceiling_aborts_with_source():
    # An operator misconfiguring default > ceiling is caught too.
    with pytest.raises(
        LimitsError, match=r"server default.*exceeds the server ceiling"
    ):
        resolve_limits({}, {"memory": "4G"}, {"memory": "2G"})


def test_resolve_value_at_ceiling_is_allowed():
    r = resolve_limits({"memory": "2G", "cpu": 4.0}, {}, {"memory": "2G", "cpu": 4.0})
    assert r.memory == "2G"
    assert r.cpu == 4.0


# --- to_cgroup_args -------------------------------------------------------


def test_to_cgroup_args_full():
    r = ResolvedLimits(memory="512M", cpu=1.5, processes=256)
    assert to_cgroup_args(r) == {
        "memory_max": 512 * 1024**2,
        "cpu_max": "150000 100000",
        "pids_max": 256,
    }


def test_to_cgroup_args_partial_only_set_dims():
    assert to_cgroup_args(ResolvedLimits(processes=64)) == {"pids_max": 64}


def test_as_dict_round_trips_hop3_toml_form():
    assert ResolvedLimits(memory="512M", cpu=1.5).as_dict() == {
        "memory": "512M",
        "cpu": 1.5,
    }
