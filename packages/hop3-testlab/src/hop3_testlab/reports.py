# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Narrative run report: an actionable, copy-pasteable markdown summary of a run.

The run-detail table is for scanning; this is for *acting*. It leads with what
broke and why — failures grouped by classification (build / addon / crash /
proxy / timeout), each with its diagnostic headline and links to the actual
logs — so an operator (or an issue tracker) gets the debugging picture without
clicking through every row. Pure functions only (functional core); the
controller renders the markdown to HTML and handles export.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from hop3_testlab.trends import RunDiff

# Classification buckets in the order we want them surfaced, with friendly
# headings. The keys are the `classify()` taxonomy from hop3_testing.bundle.
_BUCKETS: list[tuple[str, str]] = [
    ("build-failure", "Build failures"),
    ("addon-unreachable", "Addon unreachable"),
    ("app-crash", "App crashes"),
    ("proxy-502", "Proxy 502 — nothing listening on the upstream port"),
    ("timeout", "Timeouts (no response / hung)"),
    ("indeterminate", "Indeterminate (probe couldn't see enough to judge)"),
    ("other", "Other failures"),
]
_BUCKET_LABELS = dict(_BUCKETS)
_BUCKET_ORDER = [key for key, _ in _BUCKETS]

_FAIL_STATES = {"fail", "error"}


def _is_failure(row: dict) -> bool:
    """A row that needs action: failed or errored (not xpass/xfail/skip/pass)."""
    status = row.get("status")
    if status in _FAIL_STATES:
        return True
    return status is None and not row.get("passed")


def _bucket(row: dict) -> str:
    """Map a failing row to a known classification bucket (or 'other')."""
    classification = (row.get("classification") or "").strip()
    return classification if classification in _BUCKET_LABELS else "other"


def _group_failures(results: Iterable[dict]) -> dict[str, list[dict]]:
    """Failing rows grouped by bucket, in surfacing order, apps sorted within."""
    grouped: dict[str, list[dict]] = {}
    for row in results:
        if _is_failure(row):
            grouped.setdefault(_bucket(row), []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda r: r.get("app") or r.get("test_name") or "")
    return {key: grouped[key] for key in _BUCKET_ORDER if key in grouped}


def _fmt_duration(seconds: float | None) -> str:
    return f"{seconds:.1f}s" if seconds else "—"


def _fenced(content: str) -> list[str]:
    """
    Wrap untrusted content in a code fence longer than any backtick run inside.

    Python-Markdown passes raw HTML through, but content *inside* a fenced block
    is HTML-escaped. Choosing a fence longer than the longest backtick run in the
    content guarantees the content can't terminate the fence early and break out
    into raw HTML — so test output can't inject markup into the report.
    """
    longest = run = 0
    for ch in content:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}text", content, fence]


def _failure_block(row: dict) -> list[str]:
    """Markdown lines for a single failure: heading, diagnostic, links."""
    app = row.get("app") or row.get("test_name") or "?"
    variant = row.get("variant") or ""
    title = f"{app} ({variant})" if variant else app
    # Escape: heading text is rendered as markdown, which passes raw HTML through.
    lines = [f"#### {html.escape(title)}", ""]

    headline = (row.get("headline") or "").strip()
    error = (row.get("error") or "").strip()
    if headline:
        lines += [*_fenced(headline), ""]
        if error and error != headline:
            lines += [*_fenced(error), ""]
    elif error:
        lines += [*_fenced(error), ""]

    links = []
    if row.get("id") is not None:
        links.append(f"[build page](/builds/{row['id']})")
    bundle = row.get("bundle_run_id")
    if bundle:
        links.append(f"[logs / bundle](/bundle/{bundle})")
    if links:
        lines.append(" · ".join(links))
    # The headline already carries the `why` command; add it only when missing.
    if bundle and not headline:
        section = (row.get("classification") or "").strip()
        suffix = f" --section {section}" if section else ""
        lines.append(f"`hop3-test why {bundle}{suffix}`")
    lines.append("")
    return lines


def _inline_code(text: object) -> str:
    """
    Inline-code a value safely: strip backticks so it can't break out of the
    span (the report is rendered with ``| safe``).
    """
    return f"`{str(text).replace('`', '')}`"


def build_run_report_md(
    run: dict, results: list[dict], diff: RunDiff | None = None
) -> str:
    """
    Build the actionable markdown report for a run.

    Args:
        run: the ``run_row`` dict built by the runs controller.
        results: the ``result_rows`` dicts (one per test).
        diff: optional ``diff_results`` output (regressions/fixed/still_failing).

    Returns:
        A markdown string (also what the copy-to-clipboard / .md export uses).
    """
    total = run.get("total") or 0
    passed = run.get("passed") or 0
    failed = run.get("failed") or 0

    lines: list[str] = [f"# Run {html.escape(str(run.get('run_uid', '?')))}", ""]

    target = " ".join(p for p in (run.get("target_type"), run.get("target_name")) if p)
    summary = (
        f"**{html.escape(str(run.get('mode') or '—'))}**"
        + (f" on **{html.escape(target)}**" if target else "")
        + f" · {passed}/{total} passed · {failed} failed"
        + f" · {_fmt_duration(run.get('duration'))}"
    )
    lines += [summary, ""]
    meta_bits = []
    if run.get("git_sha"):
        meta_bits.append(f"git {_inline_code(run['git_sha'])}")
    if run.get("started_at"):
        meta_bits.append(f"started {html.escape(str(run['started_at']))}")
    if meta_bits:
        lines += [" · ".join(meta_bits), ""]
    if not run.get("finished_at"):
        lines += ["> ⚠ Partial — the run is still in progress.", ""]

    # Regressions first: the newest breakages relative to the previous run.
    if diff and diff.get("regressions"):
        regressions = diff["regressions"]
        lines += [f"## Regressions ({len(regressions)})", ""]
        for name in regressions:
            lines.append(f"- {_inline_code(name)}")
        lines.append("")

    grouped = _group_failures(results)
    failure_total = sum(len(rows) for rows in grouped.values())

    if failure_total:
        lines += [f"## Failures ({failure_total})", ""]
        for key, rows in grouped.items():
            lines += [f"### {_BUCKET_LABELS[key]} ({len(rows)})", ""]
            for row in rows:
                lines += _failure_block(row)
    else:
        lines += ["## Failures", "", "None 🎉", ""]

    # Passing: a count, not an enumeration (the focus is debugging).
    lines += ["## Passing", ""]
    if failed == 0 and failure_total == 0:
        lines.append(f"All {total} tests passed.")
    else:
        lines.append(
            f"{passed}/{total} passed; the {failure_total} failures above need attention."
        )
    lines.append("")

    return "\n".join(lines)
