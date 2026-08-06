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
from typing import TYPE_CHECKING, Any, ClassVar

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

    #: Reports for applications the corpus has dropped. Kept as a record, not
    #: checked against recipes — there are none left to check against.
    WITHDRAWN_DIR: ClassVar[str] = "withdrawn"

    def report_paths(self) -> list[Path]:
        """Every current report, excluding the aggregate and the template."""
        return sorted(
            p
            for p in self.reports_dir.glob("*.md")
            if not p.name.startswith("00") and p.name != "TEMPLATE.md"
        )

    def withdrawn_paths(self) -> list[Path]:
        """Every report filed under `withdrawn/`."""
        directory = self.reports_dir / self.WITHDRAWN_DIR
        return sorted(directory.glob("*.md")) if directory.is_dir() else []

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
        if path.exists():
            return path
        # The catalog is the other home of a native recipe — for some apps the
        # only one. uptime-kuma is packaged there and nowhere else, so looking
        # only under apps/real-apps-native/ reported a working, published
        # application as having no recipe at all.
        if variant == "native":
            catalog = self.root.parent / "hop3-catalog" / "apps" / app / "hop3.toml"
            if catalog.exists():
                return catalog
        return None

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

    variants = meta.get("variants")
    if not isinstance(variants, dict) or not variants:
        fail("variants must be a non-empty mapping")
        return findings
    for variant, spec in variants.items():
        _check_variant(meta["app"], variant, spec, corpus, fail)

    # Staleness, mechanically: did the thing this report describes change after
    # the report was last confirmed by a run?
    #
    # Not asked of a withdrawn report. Withdrawal says the application left the
    # corpus and the document is kept as a record, so "re-run and update
    # last_verified" is advice for work nobody is going to do — and four such
    # lines in the output are four reasons to stop reading it.
    if verified is not None and meta.get("report_status") != "withdrawn":
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

    # A run that scanned nothing must not read as a pass. Renaming the reports
    # or moving the directory would otherwise turn this whole check into a
    # green line reporting on an empty set.
    if not corpus.report_paths():
        findings.append(
            Finding("(corpus)", f"no reports found under {corpus.reports_dir}")
        )

    findings.extend(_check_withdrawn(corpus))
    findings.extend(_check_coverage(root, described))
    return findings


def _check_withdrawn(corpus: Corpus) -> list[Finding]:
    """
    The `withdrawn/` directory and the `report_status` field must agree.

    Withdrawal is expressed twice — by where the file lives and by what its
    header says — and two representations of one fact drift. A current report
    filed under `withdrawn/` would silently stop being checked against its
    recipes, which is exactly the failure the directory exists to make visible.
    """
    findings: list[Finding] = []
    for path in corpus.withdrawn_paths():
        meta = parse_frontmatter(path)
        if meta is None:
            findings.append(
                Finding(f"{corpus.WITHDRAWN_DIR}/{path.name}", "no YAML frontmatter")
            )
        elif meta.get("report_status") != "withdrawn":
            findings.append(
                Finding(
                    f"{corpus.WITHDRAWN_DIR}/{path.name}",
                    f"filed under {corpus.WITHDRAWN_DIR}/ but report_status is "
                    f"{meta.get('report_status')!r}; move it back or withdraw it",
                )
            )
    for path in corpus.report_paths():
        meta = parse_frontmatter(path)
        if meta and meta.get("report_status") == "withdrawn":
            findings.append(
                Finding(
                    path.name,
                    f"report_status is 'withdrawn' but the file is not in "
                    f"{corpus.WITHDRAWN_DIR}/",
                )
            )
    return findings


#: Written by scripts/make-nix-variants.py into every entry it generates.
_GENERATED_MARKER = "# GENERATED by scripts/make-nix-variants.py"


def _catalog_apps(catalog_dir: Path) -> set[str]:
    """
    The APPLICATIONS the catalog carries, not the directories.

    `<app>-nix` and `<app>-nixgen` are build output: the variant generator
    writes them from the corpus and removes them on `--clean`. One report covers
    all of an application's variants — that is what the header's `variants:`
    mapping is for — so requiring a separate report per generated directory asks
    for 55 documents where the design calls for 20.
    """
    apps: set[str] = set()
    for path in sorted(catalog_dir.iterdir()):
        recipe = path / "hop3.toml"
        if not path.is_dir() or not recipe.is_file():
            continue
        if recipe.read_text().startswith(_GENERATED_MARKER):
            continue
        apps.add(path.name)
    return apps


def _check_coverage(root: Path, described: set[str]) -> list[Finding]:
    """Every catalog app needs a report; reports must describe a real app."""
    findings: list[Finding] = []
    catalog_dir = root.parent / "hop3-catalog" / "apps"
    if not catalog_dir.is_dir():
        return findings  # catalog checked out elsewhere; not this tool's problem
    catalog = _catalog_apps(catalog_dir)
    for app in sorted(catalog - described):
        findings.append(Finding("(coverage)", f"catalog app {app!r} has no report"))
    # The other direction, which the module docstring promises and which nothing
    # implemented: five reports described applications the corpus had dropped
    # (adminer, focalboard, grafana, jenkins, wiki-js) and no check said so.
    # `report_status: withdrawn` is how such a report stays as a record without
    # claiming to describe something current.
    for app in sorted(described - catalog):
        findings.append(
            Finding(
                "(coverage)",
                f"report describes {app!r}, which the catalog does not carry; "
                f"mark it report_status: withdrawn or remove it",
            )
        )
    return findings


def format_findings(findings: list[Finding]) -> str:
    """A short report, grouped by file."""
    if not findings:
        return "experience reports: OK"
    lines = [f"experience reports: {len(findings)} problem(s)"]
    for f in findings:
        lines.append(f"  {f.report}: {f.message}")
    return "\n".join(lines)


def bundle_markdown(
    root: Path, title: str = "Hop3 — Application Experience Reports"
) -> str:
    """
    Concatenate the aggregate and every report into one Markdown document.

    `md2pdf` refuses `-o` with several inputs (each would become its own PDF),
    so a single deliverable needs a single file. Two details matter:

    - **Only the bundle carries frontmatter.** Each report's own header is
      stripped: a second `---` block partway through a document is not metadata,
      it renders as a horizontal rule and a wall of YAML.
    - **The bundle is written beside the reports**, so every relative image path
      (`images/<app>-01-login.png`) still resolves.

    Headings are not re-levelled. Each report starts at `#`, which makes it a
    chapter of the bundle — the structure a reader wants.
    """
    corpus = Corpus(root)
    parts = [
        f"---\ntitle: {title}\n---\n",
        "# Application Experience Reports\n",
        (
            "One report per packaged application, plus the aggregate. Generated "
            "by `make reports-pdf`; validated by `hop3-tools catalog reports`.\n"
        ),
    ]

    aggregate = corpus.reports_dir / "00-aggregate.md"
    ordered = ([aggregate] if aggregate.exists() else []) + corpus.report_paths()

    for path in ordered:
        text = path.read_text()
        # Drop the report's own frontmatter; the bundle supplies the document's.
        match = FRONTMATTER_RE.match(text)
        body = text[match.end() :] if match else text
        parts.append(body.strip())

    # Separated by a rule, not a page break. `\pagebreak` is LaTeX and this
    # renders through Typst, where it came out as literal text in the PDF; and
    # neither a `{=typst}` raw block nor `--class report` breaks on a level-1
    # heading. Making each report start a page wants a Typst stylesheet with a
    # `show heading.where(level: 1)` rule, passed via `md2pdf --stylesheet`.
    # Until that exists, a visible rule beats a broken directive.
    return "\n\n---\n\n".join(parts) + "\n"
