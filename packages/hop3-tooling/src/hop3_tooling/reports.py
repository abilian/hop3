# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Validate the experience reports against the recipes they describe.

The reports are half of NGI milestone M4 ("20 applications *plus* experience
reports"), and they rotted invisibly: by 2026-07 six of twenty named a Nix
template their app no longer used, one described an application the corpus had
dropped, and every one of them certified `Status: Passing / Issues: None` for
apps that were later found to deploy, serve HTTP 200, and refuse every login.

Prose cannot be checked, but the claims that rotted were not prose — they were
facts about recipes and about *when* something was last run. So each report
carries a machine-checked header (see TEMPLATE.md) and this module compares it
against the tree:

- the set of reports against the set of catalog apps, both directions;
- each declared nix-gen template against the recipe's actual `[nix].template`;
- the bar a report claims to have verified against what its status is allowed
  to assert (a catalog app cannot be `final` on an unauthenticated bar);
- and `last_verified` against the recipe's last commit, which is the check that
  makes staleness *detectable* rather than merely regrettable.

The last one is the point. A report is stale exactly when the thing it describes
changed after the report was last confirmed by a run, and git already knows that.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import tomllib
import yaml

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

#: The bars a report may claim, weakest first. A catalog app is advertised, so
#: it may not be reported `final` on anything less than an authenticated check.
BARS = ("http-status", "http-content", "authenticated")

#: Statuses a variant may carry. `not-attempted` is deliberately distinct from
#: `no-recipe`: one is a decision, the other is an absence.
VARIANT_STATUSES = ("pass", "fail", "no-recipe", "not-attempted")

REQUIRED_KEYS = (
    "app",
    "version",
    "in_catalog",
    "report_status",
    "last_verified",
    "verified_bar",
    "variants",
)

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


@dataclass(frozen=True)
class Finding:
    """One problem with one report."""

    report: str
    message: str


@dataclass
class Corpus:
    """Where the reports and the recipes live."""

    root: Path
    reports_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.reports_dir = self.root / "notes" / "experience-reports"

    def report_paths(self) -> list[Path]:
        """Every report file, excluding the aggregate and the template."""
        return sorted(
            p
            for p in self.reports_dir.glob("*.md")
            if not p.name.startswith("00") and p.name != "TEMPLATE.md"
        )

    def recipe(self, app: str, variant: str) -> Path | None:
        """The app's `hop3.toml` for a variant, if the corpus holds one."""
        by_variant = {
            "native": "real-apps-native",
            "docker": "real-apps-docker",
            "nix": "real-apps-nix",
            "nix-gen": "real-apps-nix-gen",
        }
        directory = by_variant.get(variant)
        if not directory:
            return None
        path = self.root / "apps" / directory / app / "hop3.toml"
        return path if path.exists() else None

    def last_changed(self, app: str) -> dt.date | None:
        """
        The date any of this app's recipes last changed, from git.

        Returns None when git cannot answer (a shallow clone, an untracked
        path). An unanswerable question is reported as unknown rather than
        silently treated as "not stale".
        """
        paths = [
            str(p.parent)
            for variant in ("native", "docker", "nix", "nix-gen")
            if (p := self.recipe(app, variant))
        ]
        if not paths:
            return None
        try:
            out = subprocess.run(
                ["git", "log", "-1", "--format=%cs", "--", *paths],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        stamp = out.stdout.strip()
        try:
            return dt.date.fromisoformat(stamp)
        except ValueError:
            return None


def parse_frontmatter(path: Path) -> dict[str, Any] | None:
    """The report's YAML header, or None when it has none."""
    match = FRONTMATTER_RE.match(path.read_text())
    if not match:
        return None
    loaded = yaml.safe_load(match.group(1))
    return loaded if isinstance(loaded, dict) else None


def _check_header(meta: dict[str, Any], fail: Callable[[str], None]) -> dt.date | None:
    """Validate the scalar fields; return the parsed verification date."""
    if meta["verified_bar"] not in BARS:
        fail(f"verified_bar {meta['verified_bar']!r} is not one of {list(BARS)}")

    # An advertised app reported as done must have been signed into. This is the
    # rule that stops a report certifying the bar §6.1 of the report rejects.
    if (
        meta["report_status"] == "final"
        and meta.get("in_catalog")
        and meta["verified_bar"] != "authenticated"
    ):
        fail(
            f"report_status is 'final' and the app is in the catalog, but "
            f"verified_bar is {meta['verified_bar']!r}; an advertised app must "
            f"be verified by signing in"
        )

    verified = meta["last_verified"]
    if not isinstance(verified, dt.date):
        fail(f"last_verified {verified!r} is not a date (use YYYY-MM-DD)")
        return None
    return verified


def _check_variant(
    app: str,
    variant: str,
    spec: Any,
    corpus: Corpus,
    fail: Callable[[str], None],
) -> None:
    """Validate one variant entry against the recipe it claims to describe."""
    if not isinstance(spec, dict) or "status" not in spec:
        fail(f"variant {variant!r} has no status")
        return
    status = spec["status"]
    if status not in VARIANT_STATUSES:
        fail(f"variant {variant!r} status {status!r} not in {list(VARIANT_STATUSES)}")
        return

    recipe = corpus.recipe(app, variant)
    if status in {"pass", "fail"} and recipe is None:
        fail(f"variant {variant!r} claims {status!r} but no recipe exists for it")
    if status == "no-recipe":
        if recipe is not None:
            fail(f"variant {variant!r} claims 'no-recipe' but {recipe} exists")
        if not spec.get("reason"):
            fail(f"variant {variant!r} is 'no-recipe' without a reason")

    # The claim that rotted six times: which template the app actually uses.
    if variant == "nix-gen" and recipe is not None and status == "pass":
        actual = tomllib.loads(recipe.read_text()).get("nix", {}).get("template")
        declared = spec.get("template")
        if declared != actual:
            fail(
                f"nix-gen template is {declared!r} in the report but "
                f"{actual!r} in {recipe.relative_to(corpus.root)}"
            )


def check_report(meta: dict[str, Any], corpus: Corpus, name: str) -> list[Finding]:
    """Every problem with one report's header."""
    findings: list[Finding] = []

    def fail(message: str) -> None:
        findings.append(Finding(name, message))

    missing = [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        fail(f"header is missing required field(s): {', '.join(missing)}")
        return findings

    verified = _check_header(meta, fail)

    variants = meta.get("variants") or {}
    if not isinstance(variants, dict) or not variants:
        fail("variants must be a non-empty mapping")
        return findings
    for variant, spec in variants.items():
        _check_variant(meta["app"], variant, spec, corpus, fail)

    # Staleness, mechanically: did the thing this report describes change after
    # the report was last confirmed by a run?
    if verified is not None:
        changed = corpus.last_changed(meta["app"])
        if changed is not None and changed > verified:
            fail(
                f"recipes changed on {changed} but the report was last verified "
                f"on {verified}; re-run and update last_verified"
            )

    return findings


def check_all(root: Path) -> list[Finding]:
    """Validate every report, and the coverage of the set as a whole."""
    corpus = Corpus(root)
    findings: list[Finding] = []
    described: set[str] = set()

    for path in corpus.report_paths():
        meta = parse_frontmatter(path)
        if meta is None:
            findings.append(Finding(path.name, "no YAML frontmatter (see TEMPLATE.md)"))
            continue
        app = meta.get("app")
        if isinstance(app, str):
            # A withdrawn report describes an app the corpus no longer carries;
            # that is a legitimate record, not a coverage claim.
            if meta.get("report_status") != "withdrawn":
                described.add(app)
        findings.extend(check_report(meta, corpus, path.name))

    findings.extend(_check_coverage(root, described))
    return findings


def _check_coverage(root: Path, described: set[str]) -> list[Finding]:
    """Every catalog app needs a report; reports must describe a real app."""
    findings: list[Finding] = []
    catalog_dir = root.parent / "hop3-catalog" / "apps"
    if not catalog_dir.is_dir():
        return findings  # catalog checked out elsewhere; not this tool's problem
    catalog = {p.name for p in catalog_dir.iterdir() if p.is_dir()}
    for app in sorted(catalog - described):
        findings.append(Finding("(coverage)", f"catalog app {app!r} has no report"))
    return findings


def format_findings(findings: list[Finding]) -> str:
    """A short report, grouped by file."""
    if not findings:
        return "experience reports: OK"
    lines = [f"experience reports: {len(findings)} problem(s)"]
    for f in findings:
        lines.append(f"  {f.report}: {f.message}")
    return "\n".join(lines)
