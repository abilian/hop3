# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Regenerate the paper's tables and figures from a raw measurement run.

Every number quoted in the paper's evaluation section must come out of here, so
that no figure is hand-transcribed and each one traces to the run that produced
it. These are pure functions over the parsed JSON — no I/O, so they are testable
without a live box.
"""

from __future__ import annotations

from operator import itemgetter
from statistics import median
from typing import Any


def render_closure_table(data: dict[str, Any]) -> str:
    """The closure-versus-image table (uncompressed), ordered by closure size."""
    block = data.get("closure_vs_image") or {}
    rows = sorted(block.get("rows") or [], key=itemgetter("nix_closure_mb"))
    if not rows:
        msg = "no closure_vs_image rows in the run"
        raise ValueError(msg)
    out = [
        "| Application | Nix closure | Store paths | Docker image | Nix update delta† |",
        "|-------------|-------------|-------------|--------------|-------------------|",
    ]
    for r in rows:
        out.append(
            f"| {r['app'].capitalize()} {r['version']} | {r['nix_closure_mb']} MB "
            f"| {r['nix_paths']} | {r['docker_mb']} MB | {r['update_delta_mb']} MB |"
        )
    return "\n".join(out)


def render_dedup(data: dict[str, Any]) -> str:
    """The cross-application deduplication sentence, both homogeneity regimes."""
    d = data.get("dedup") or {}
    homo, mixed = d.get("homogeneous_4_go"), d.get("mixed_6")
    if not homo or not mixed:
        msg = "run is missing one of the dedup regimes"
        raise ValueError(msg)
    return (
        f"Deduplication saves {homo['saving_pct']}% across the "
        f"{len(homo['apps'])} homogeneous (Go) applications "
        f"({homo['union_mb']} MB union against {homo['sum_individual_mb']} MB summed) "
        f"and {mixed['saving_pct']}% across all {len(mixed['apps'])} "
        f"({mixed['union_mb']} MB against {mixed['sum_individual_mb']} MB)."
    )


def render_deploy_timing(data: dict[str, Any]) -> str:
    """The build-and-install band, with the cold-install figure."""
    t: dict[str, Any] = data.get("deploy_timing") or {}
    per_app = sorted(t.get("per_app_s") or [], key=itemgetter("seconds"))
    if not per_app:
        msg = "no deploy timings in the run"
        raise ValueError(msg)
    cold = t.get("cold_install_blank_to_app_s")
    if cold is None:
        msg = "deploy_timing has no cold_install_blank_to_app_s figure"
        raise ValueError(msg)
    lo, hi = per_app[0]["seconds"], per_app[-1]["seconds"]
    detail = ", ".join(f"{r['app']} ({r['builder']}) {r['seconds']} s" for r in per_app)
    return (
        f"A blank server reaches a running, verified application in {cold} s "
        f"(~{round(cold / 60)} min). With the platform installed, a further "
        f"application takes {lo}–{hi} s: {detail}."
    )


def render_baselines(data: dict[str, Any]) -> str:
    """The control-plane comparison, computed like-for-like (same workload)."""
    b = data.get("control_plane_baselines") or {}
    stacks = {s["stack"]: s for s in (b.get("stacks") or [])}
    hop3, k3s, compose = (
        stacks.get("hop3"),
        stacks.get("k3s"),
        stacks.get("docker-compose"),
    )
    if not (hop3 and k3s and compose):
        msg = "baselines need all three stacks (hop3, k3s, docker-compose)"
        raise ValueError(msg)
    h = hop3["cgroup_mb"]
    loaded = k3s["with_1_pod_cgroup_mb"]
    idle = k3s["idle_cgroup_mb"]
    return (
        f"Hop3 {h} MB with one application; K3s {idle} MB idle and {loaded} MB with "
        f"one pod; Docker Compose {compose['idle_cgroup_mb']} MB idle and "
        f"{compose['with_1_container_mb']} MB with one container. Like for like "
        f"(same metric, same workload) Hop3 is {round(loaded / h, 1)}× lighter than "
        f"K3s, and {round(idle / h, 1)}× lighter than an idle K3s."
    )


def render_all(data: dict[str, Any]) -> str:
    """Every regenerable figure, in the order the paper presents them."""
    run = data.get("run", "unknown-run")
    parts = [
        f"# Measurement run: {run}",
        "",
        "## Closure versus image (Table 3)",
        "",
        render_closure_table(data),
        "",
        "## Deduplication",
        "",
        render_dedup(data),
        "",
        "## Build-and-install time",
        "",
        render_deploy_timing(data),
        "",
        "## Control-plane footprint versus baselines",
        "",
        render_baselines(data),
    ]
    return "\n".join(parts)


def render_matrix(cells: list[dict[str, Any]]) -> str:
    """
    Render the golden-app matrix: per-variant deploy time and coverage.

    Takes the JSONL cells produced by ``hop3-bench matrix``. Successful cells
    carry the timing; failed and no-recipe cells are counted but never averaged
    into it, so a variant's median is the cost of a deploy that *worked*.
    """
    variants = ["native", "docker", "nix", "nix-gen"]
    lines = [
        "| Variant | Deployed | Failed | No recipe | Median | Mean | Range |",
        "|---------|---------:|-------:|----------:|-------:|-----:|-------|",
    ]
    for variant in variants:
        rows = [c for c in cells if c.get("variant") == variant]
        if not rows:
            continue
        ok = [c["seconds"] for c in rows if c.get("status") == "ok"]
        failed = sum(1 for c in rows if c.get("status") == "failed")
        absent = sum(1 for c in rows if c.get("status") == "no-recipe")
        if not ok:
            lines.append(f"| {variant} | 0 | {failed} | {absent} | — | — | — |")
            continue
        lines.append(
            f"| {variant} | {len(ok)} | {failed} | {absent} | "
            f"{int(median(ok))} s | {int(sum(ok) / len(ok))} s | "
            f"{min(ok)}–{max(ok)} s |"
        )

    failures = [c for c in cells if c.get("status") == "failed"]
    if failures:
        lines.append("")
        lines.append("Failed cells:")
        lines.extend(
            f"- `{c['variant']}/{c['app']}` ({c.get('seconds', '?')} s) — "
            f"{c.get('reason', 'no diagnostic')}"
            for c in failures
        )
    return "\n".join(lines)
