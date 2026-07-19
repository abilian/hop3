# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the benchmark probe parsers (no I/O)."""

from __future__ import annotations

import pytest
from hop3_tooling.bench.probes import (
    BenchError,
    ControlPlaneMemory,
    control_plane_memory,
    parse_closure,
    parse_docker_size,
    parse_pss_kb,
)

# Captured from the 2026-07-19 dev-box run (see local-notes/benchmarks/).
SMAPS_ROLLUP = """\
55f0a0000000-7ffd00000000 ---p 00000000 00:00 0    [rollup]
Rss:              126008 kB
Pss:               96982 kB
Pss_Anon:          90000 kB
Shared_Clean:      12000 kB
"""

PATH_INFO_LIST = """\
[{"path":"/nix/store/x-miniflux","narSize":40000000,"narHash":"sha256-a"},
 {"path":"/nix/store/y-glibc","narSize":14829928,"narHash":"sha256-b"}]
"""

PATH_INFO_DICT = """\
{"/nix/store/x-miniflux":{"narSize":40000000},"/nix/store/y-glibc":{"narSize":14829928}}
"""


def test_parse_pss_sums_the_field():
    assert parse_pss_kb(SMAPS_ROLLUP) == 96982


def test_parse_pss_raises_when_absent():
    with pytest.raises(BenchError, match="no Pss"):
        parse_pss_kb("Rss: 100 kB\n")


def test_parse_closure_list_form():
    info = parse_closure(PATH_INFO_LIST)
    assert info.closure_bytes == 54829928
    assert info.path_count == 2
    assert info.closure_mb == 54.8


def test_parse_closure_dict_form():
    info = parse_closure(PATH_INFO_DICT)
    assert info.closure_bytes == 54829928
    assert info.path_count == 2


def test_parse_closure_rejects_empty():
    with pytest.raises(BenchError, match="empty"):
        parse_closure("[]")


def test_parse_docker_size():
    assert parse_docker_size("  12265288\n") == 12265288


def test_parse_docker_size_rejects_non_numeric():
    with pytest.raises(BenchError, match="not a number"):
        parse_docker_size("<no value>")


def test_control_plane_memory_raises_on_empty_process_set():
    # A swallowed empty process set would report zero memory — must fail loud.
    with pytest.raises(BenchError, match="not running"):
        control_plane_memory(lambda cmd: "")


def test_control_plane_memory_sums_over_pids():
    responses = {
        "pgrep -f 'hop3-server serve'": "10\n20\n",
        "cat /proc/10/smaps_rollup": "Pss: 100 kB\n",
        "cat /proc/20/smaps_rollup": "Pss: 50 kB\n",
        "grep VmRSS /proc/10/status": "VmRSS: 200 kB\n",
        "grep VmRSS /proc/20/status": "VmRSS: 80 kB\n",
    }
    mem = control_plane_memory(lambda cmd: responses[cmd])
    assert isinstance(mem, ControlPlaneMemory)
    assert mem.pss_kb == 150
    assert mem.rss_kb == 280
    assert mem.pids == (10, 20)
