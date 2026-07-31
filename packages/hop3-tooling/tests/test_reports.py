# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The experience-report checker.

Each test below corresponds to a way the real reports actually went wrong
between April and July 2026, so the suite is a record of the failure modes as
much as a test of the code.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import textwrap
from typing import TYPE_CHECKING

import pytest
from hop3_tooling import reports

if TYPE_CHECKING:
    from pathlib import Path


def _write_report(root: Path, name: str, header: str, body: str = "# Report\n") -> Path:
    d = root / "notes" / "experience-reports"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(f"---\n{textwrap.dedent(header).strip()}\n---\n\n{body}")
    return p


def _write_recipe(root: Path, variant: str, app: str, toml: str = "") -> Path:
    d = root / "apps" / f"real-apps-{variant}" / app
    d.mkdir(parents=True, exist_ok=True)
    p = d / "hop3.toml"
    p.write_text(toml or '[metadata]\nid = "x"\n')
    return p


GOOD = """
app: demo
version: "1.0"
in_catalog: true
report_status: final
last_verified: 2026-07-28
verified_bar: authenticated
variants:
  native: {status: pass}
"""


def test_a_well_formed_report_passes(tmp_path: Path) -> None:
    _write_report(tmp_path, "01-demo.md", GOOD)
    _write_recipe(tmp_path, "native", "demo")

    meta = reports.parse_frontmatter(tmp_path / "notes/experience-reports/01-demo.md")
    assert meta is not None
    assert reports.check_report(meta, reports.Corpus(tmp_path), "01-demo.md") == []


def test_missing_frontmatter_is_reported(tmp_path: Path) -> None:
    """Every report as of 2026-07 had none."""
    p = tmp_path / "notes" / "experience-reports" / "01-demo.md"
    p.parent.mkdir(parents=True)
    p.write_text("# Experience Report: Demo\n\n**Status:** Draft (0.5)\n")
    assert reports.parse_frontmatter(p) is None


def test_declared_nix_gen_template_must_match_the_recipe(tmp_path: Path) -> None:
    """Six of twenty reports named a template their app no longer used."""
    _write_report(
        tmp_path,
        "01-demo.md",
        """
        app: demo
        version: "1.0"
        in_catalog: true
        report_status: final
        last_verified: 2026-07-28
        verified_bar: authenticated
        variants:
          nix-gen: {status: pass, template: prebuilt-binary}
        """,
    )
    _write_recipe(tmp_path, "nix-gen", "demo", '[nix]\ntemplate = "go-source"\n')

    meta = reports.parse_frontmatter(tmp_path / "notes/experience-reports/01-demo.md")
    findings = reports.check_report(meta, reports.Corpus(tmp_path), "01-demo.md")

    assert len(findings) == 1
    assert "prebuilt-binary" in findings[0].message
    assert "go-source" in findings[0].message


def test_catalog_app_cannot_be_final_on_an_unauthenticated_bar(tmp_path: Path) -> None:
    """
    The deep defect: every report certified `Passing / Issues: None` on apps
    that served 200 and refused every login.
    """
    _write_report(
        tmp_path,
        "01-demo.md",
        """
        app: demo
        version: "1.0"
        in_catalog: true
        report_status: final
        last_verified: 2026-07-28
        verified_bar: http-status
        variants:
          native: {status: pass}
        """,
    )
    _write_recipe(tmp_path, "native", "demo")

    meta = reports.parse_frontmatter(tmp_path / "notes/experience-reports/01-demo.md")
    findings = reports.check_report(meta, reports.Corpus(tmp_path), "01-demo.md")

    assert any("signing in" in f.message for f in findings)


def test_a_variant_claiming_pass_needs_a_recipe(tmp_path: Path) -> None:
    """focalboard's report described four passing variants and had no recipe."""
    _write_report(tmp_path, "01-demo.md", GOOD)  # native: pass, but no recipe written

    meta = reports.parse_frontmatter(tmp_path / "notes/experience-reports/01-demo.md")
    findings = reports.check_report(meta, reports.Corpus(tmp_path), "01-demo.md")

    assert any("no recipe exists" in f.message for f in findings)


def test_no_recipe_needs_a_reason(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        "01-demo.md",
        """
        app: demo
        version: "1.0"
        in_catalog: false
        report_status: draft
        last_verified: 2026-07-28
        verified_bar: authenticated
        variants:
          nix: {status: no-recipe}
        """,
    )
    meta = reports.parse_frontmatter(tmp_path / "notes/experience-reports/01-demo.md")
    findings = reports.check_report(meta, reports.Corpus(tmp_path), "01-demo.md")
    assert any("without a reason" in f.message for f in findings)


@pytest.mark.parametrize("missing", ["app", "version", "last_verified", "verified_bar"])
def test_required_header_fields(tmp_path: Path, missing: str) -> None:
    header = {
        "app": "demo",
        "version": '"1.0"',
        "in_catalog": "false",
        "report_status": "draft",
        "last_verified": "2026-07-28",
        "verified_bar": "authenticated",
    }
    del header[missing]
    body = "\n".join(f"{k}: {v}" for k, v in header.items())
    _write_report(
        tmp_path, "01-demo.md", body + "\nvariants:\n  native: {status: pass}\n"
    )

    meta = reports.parse_frontmatter(tmp_path / "notes/experience-reports/01-demo.md")
    findings = reports.check_report(meta, reports.Corpus(tmp_path), "01-demo.md")
    assert any(missing in f.message for f in findings)


def test_a_recipe_changed_after_last_verified_is_stale(tmp_path: Path) -> None:
    """
    The check that makes rot detectable rather than merely regrettable.

    Uses a real git repo, because the staleness rule is only worth anything if
    it reads the same history a maintainer would.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)

    _write_recipe(tmp_path, "native", "demo")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "recipe", "--date", "2026-07-20T00:00:00"],
        cwd=tmp_path,
        check=True,
        env={"GIT_COMMITTER_DATE": "2026-07-20T00:00:00", "PATH": "/usr/bin:/bin"},
    )

    corpus = reports.Corpus(tmp_path)
    assert corpus.last_changed("demo") == dt.date(2026, 7, 20)

    # Verified BEFORE the recipe changed -> stale.
    _write_report(
        tmp_path,
        "01-demo.md",
        """
        app: demo
        version: "1.0"
        in_catalog: false
        report_status: draft
        last_verified: 2026-07-01
        verified_bar: authenticated
        variants:
          native: {status: pass}
        """,
    )
    meta = reports.parse_frontmatter(tmp_path / "notes/experience-reports/01-demo.md")
    findings = reports.check_report(meta, corpus, "01-demo.md")
    assert any("re-run and update last_verified" in f.message for f in findings)


def test_withdrawn_reports_do_not_claim_coverage(tmp_path: Path) -> None:
    """A withdrawn app (focalboard) is a record, not a coverage claim."""
    _write_report(
        tmp_path,
        "01-gone.md",
        """
        app: gone
        version: "1.0"
        in_catalog: false
        report_status: withdrawn
        last_verified: 2026-07-28
        verified_bar: http-status
        variants:
          native: {status: no-recipe, reason: "upstream archived"}
        """,
    )
    findings = reports.check_all(tmp_path)
    assert not any(f.report == "01-gone.md" for f in findings)
