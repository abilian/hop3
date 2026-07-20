# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the benchmark probe parsers (no I/O)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hop3_tooling.bench.probes import (
    BenchError,
    ControlPlaneMemory,
    control_plane_memory,
    parse_cgroup_bytes,
    parse_closure,
    parse_docker_size,
    parse_pss_kb,
    parse_single_path,
)
from hop3_tooling.bench.report import render_all

# Captured from the 2026-07-19 dev-box run (see notes/benchmarks/).
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


def test_parse_single_path_returns_size_and_hash():
    size, nar_hash = parse_single_path(
        '[{"path":"/nix/store/x","narSize":19397240,"narHash":"sha256-abc"}]'
    )
    assert size == 19397240
    assert nar_hash == "sha256-abc"


def test_parse_single_path_rejects_zero():
    with pytest.raises(BenchError, match="zero-byte"):
        parse_single_path('[{"path":"/nix/store/x","narSize":0}]')


def test_parse_cgroup_bytes():
    assert parse_cgroup_bytes(" 181256192\n") == 181256192


def test_parse_cgroup_bytes_rejects_non_numeric():
    with pytest.raises(BenchError, match="not a number"):
        parse_cgroup_bytes("max")


# ---- the paper's figures must be regenerable from the raw run ---------------

RUN = Path(__file__).parents[3] / "notes" / "benchmarks" / "2026-07-19-preliminary.json"


@pytest.mark.skipif(not RUN.exists(), reason="raw measurement run not present")
def test_paper_figures_regenerate_from_the_raw_run():
    """Guards the claim that no figure in the paper is hand-transcribed."""
    rendered = render_all(json.loads(RUN.read_text()))
    # closure table (Table 3)
    assert "| Miniflux 2.2.8 | 54.8 MB | 8 | 12.3 MB | 19.4 MB |" in rendered
    assert "Keycloak 26.1.4" in rendered
    # dedup, both homogeneity regimes
    assert "36.3%" in rendered
    assert "21.0%" in rendered
    # build-and-install
    assert "528 s" in rendered
    # the like-for-like control-plane ratio quoted in the paper
    assert "7.8× lighter than K3s" in rendered


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
