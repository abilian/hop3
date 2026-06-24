#!/usr/bin/env python3
# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Record asciinema screencasts of every Hop3 demo and tutorial (NGI M5.6).

Wraps each executable demo (`demos/demo.py`) and each tutorial (`validoc`) in
an `asciinema record` session, producing one `.cast` file per item. With
`--upload`, each cast is uploaded to asciinema.org and the public URL captured,
so the set of movie links can be reported to NGI/NLNet (deliverable M5.6).

This records against a server you set up yourself (e.g. hop3-dev.abilian.com).
It never reinstalls hop3 per screencast: demos run with `--skip-install`, and
tutorials target the existing server via the `hop3` CLI (HOP3_API_URL /
HOP3_TEST_DOMAIN). You install hop3 on the server once; this just runs and
records each demo/tutorial against it.

Examples:
    # List what would be recorded (no execution, no server needed):
    uv run scripts/record_screencasts.py --list

    # Record every demo + tutorial against your server:
    uv run scripts/record_screencasts.py --host hop3-dev.abilian.com

    # A subset, then upload and print the URLs for the NGI report:
    uv run scripts/record_screencasts.py --host hop3-dev.abilian.com \\
        --only demo01,flask --upload

Prerequisites:
    - asciinema (v3) and validoc on PATH (and runnable).
    - A hop3 server already installed at --host, with the `hop3` CLI able to
      reach it. This script does NOT set the server up — it only records runs
      against it. A failing demo/tutorial is still recorded and marked FAILED
      in the manifest (never silently skipped).
    - To associate uploads with your account, run `asciinema auth` first.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMOS_DIR = REPO_ROOT / "demos"
TUTORIALS_DIR = REPO_ROOT / "docs" / "tutorials"

# asciinema prints "...recording at: <url>"; grab the first http(s) URL it emits.
_URL_RE = re.compile(r"https?://\S+")


@dataclass(frozen=True, slots=True)
class Item:
    """One thing to record: a demo or a tutorial."""

    category: str  # "demo" | "tutorial"
    name: str  # stable slug, unique within a category
    command: str  # shell command that runs (and thus demonstrates) it
    env: dict[str, str] = field(default_factory=dict)  # extra env for the run


@dataclass(slots=True)
class Result:
    item: Item
    cast: Path
    recorded: bool
    returncode: int
    url: str = ""
    error: str = ""


def discover_demos(
    *, host: str, backend: str, skip_install: bool, pause: float, domain: str
) -> list[Item]:
    """Each `demos/demoNN/` (with a `demo-script.py`) is one recordable demo.

    Runs against the already-installed server at `host` (`--skip-install`),
    so hop3 is never reinstalled per demo.
    """
    base = [
        shlex.quote(sys.executable),
        shlex.quote(str(DEMOS_DIR / "demo.py")),
        "--backend",
        shlex.quote(backend),
    ]
    if host:
        base += ["--host", shlex.quote(host)]
    if domain:
        base += ["--admin-domain", shlex.quote(domain)]
    if skip_install:
        base.append("--skip-install")
    base += ["--pause", str(pause)]

    items: list[Item] = []
    for script in sorted(DEMOS_DIR.glob("demo*/demo-script.py")):
        name = script.parent.name
        cmd = " ".join([*base, shlex.quote(name)])
        items.append(Item("demo", name, cmd))
    return items


def discover_tutorials(*, host: str, domain: str) -> list[Item]:
    """Each `docs/tutorials/<lang>/*.md` (except index.md) is one tutorial.

    Tutorials deploy to the existing server via the `hop3` CLI; HOP3_API_URL
    (an SSH-tunnel URL) and HOP3_TEST_DOMAIN point them at it. No install here.
    """
    env: dict[str, str] = {}
    if host:
        env["HOP3_API_URL"] = f"ssh://root@{host}"
    if domain:
        env["HOP3_TEST_DOMAIN"] = domain

    items: list[Item] = []
    for md in sorted(TUTORIALS_DIR.glob("*/*.md")):
        if md.name == "index.md":
            continue
        name = f"{md.parent.name}-{md.stem}"  # e.g. "python-flask"
        cmd = f"validoc run {shlex.quote(str(md))}"
        items.append(Item("tutorial", name, cmd, env=dict(env)))
    return items


def record(item: Item, outdir: Path, idle: float) -> Result:
    """Run `item.command` inside `asciinema record`, writing a .cast file."""
    cast = outdir / f"{item.category}-{item.name}.cast"
    argv = [
        "asciinema",
        "record",
        "--overwrite",
        "-i",
        str(idle),
        "--command",
        item.command,
        str(cast),
    ]
    run_env = {**os.environ, **item.env} if item.env else None
    print(f"\n=== recording {item.category}:{item.name} ===")
    print(f"    $ {item.command}")
    proc = subprocess.run(argv, cwd=REPO_ROOT, check=False, env=run_env)
    # asciinema writes the cast regardless of the inner command's fate; treat a
    # non-empty file as "recorded", and surface the inner command's exit code.
    recorded = cast.is_file() and cast.stat().st_size > 0
    error = "" if recorded else "no .cast produced (asciinema record failed)"
    return Result(item, cast, recorded, proc.returncode, error=error)


def upload(result: Result, *, visibility: str, title_prefix: str) -> None:
    """Upload a cast to asciinema.org and capture the returned URL."""
    if not result.recorded:
        result.error = result.error or "skipped upload: nothing recorded"
        return
    title = f"{title_prefix}{result.item.category}: {result.item.name}".strip()
    argv = ["asciinema", "upload", "--title", title]
    if visibility:
        argv += ["--visibility", visibility]
    argv.append(str(result.cast))
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    output = f"{proc.stdout}\n{proc.stderr}"
    url = parse_upload_url(output)
    if proc.returncode == 0 and url:
        result.url = url
    else:
        result.error = f"upload failed (exit {proc.returncode}): {output.strip()[:300]}"


def parse_upload_url(output: str) -> str:
    """Extract the recording URL from asciinema's upload output (testable core)."""
    match = _URL_RE.search(output)
    return match.group(0).rstrip(".,)") if match else ""


def write_manifest(results: list[Result], outdir: Path) -> Path:
    """Write MANIFEST.md (+ .json) mapping each item to its cast and URL."""
    rows = []
    data = []
    for r in results:
        status = "ok" if r.recorded and r.returncode == 0 else "FAILED"
        url = r.url or ("—" if not r.error else f"⚠ {r.error[:60]}")
        rows.append(
            f"| {r.item.category} | {r.item.name} | {status} | "
            f"`{r.cast.name}` | {url} |"
        )
        data.append(
            {
                "category": r.item.category,
                "name": r.item.name,
                "status": status,
                "command": r.item.command,
                "cast": r.cast.name,
                "url": r.url,
                "returncode": r.returncode,
                "error": r.error,
            }
        )
    md = outdir / "MANIFEST.md"
    header = (
        "# Hop3 screencasts (NGI M5.6)\n\n"
        "Generated by `scripts/record_screencasts.py`.\n\n"
        "| Category | Name | Status | Cast | URL |\n"
        "|----------|------|--------|------|-----|\n"
    )
    md.write_text(header + "\n".join(rows) + "\n")
    (outdir / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    return md


def require_tools(items: list[Item]) -> None:
    """Fail loud, up front, if a required executable is missing or broken."""
    needs_validoc = any(i.category == "tutorial" for i in items)
    needed = ["asciinema"] + (["validoc"] if needs_validoc else [])
    missing = [t for t in needed if shutil.which(t) is None]
    if missing:
        sys.exit(
            f"[record_screencasts] required tool(s) not on PATH: {', '.join(missing)}.\n"
            "  Install asciinema (v3) and ensure validoc is available, then retry."
        )
    # validoc is a project dependency; probe that it actually runs.
    if needs_validoc:
        probe = subprocess.run(
            ["validoc", "--help"], capture_output=True, text=True, check=False
        )
        if probe.returncode != 0:
            detail = (probe.stderr or probe.stdout).strip().splitlines()
            sys.exit(
                "[record_screencasts] validoc is installed but not runnable:\n"
                f"  {detail[0] if detail else '(no output)'}\n"
                "  Reinstall it with: uv sync"
            )


def select(items: list[Item], patterns: list[str]) -> list[Item]:
    """Keep items whose name or category contains any of the substrings."""
    if not patterns:
        return items
    chosen = [i for i in items if any(p in i.name or p == i.category for p in patterns)]
    if not chosen:
        sys.exit(f"[record_screencasts] --only matched nothing: {patterns}")
    return chosen


def build_items(args: argparse.Namespace) -> list[Item]:
    items: list[Item] = []
    skip_install = not args.reinstall and args.backend == "ssh"
    if not args.tutorials_only:
        items += discover_demos(
            host=args.host,
            backend=args.backend,
            skip_install=skip_install,
            pause=args.pause,
            domain=args.domain,
        )
    if not args.demos_only:
        items += discover_tutorials(host=args.host, domain=args.domain)
    return select(items, args.only)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record asciinema screencasts of all Hop3 demos and tutorials, "
        "against a server you already set up (no reinstall per screencast).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--host", default="",
                        help="server already running hop3 (e.g. hop3-dev.abilian.com); "
                             "demos run against it with --skip-install, tutorials via "
                             "HOP3_API_URL (ssh://root@<host>)")
    parser.add_argument("--domain", default="",
                        help="app domain for tutorials (HOP3_TEST_DOMAIN) and the demo "
                             "admin UI; defaults to --host")
    parser.add_argument("--backend", default="ssh", choices=["ssh", "docker"],
                        help="demo backend (default: ssh against --host)")
    parser.add_argument("--reinstall", action="store_true",
                        help="let demos (re)install hop3 instead of --skip-install "
                             "(default: never reinstall)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "screencasts",
                        help="output directory for .cast files (default: ./screencasts)")
    parser.add_argument("--only", default="",
                        help="comma-separated substrings/categories to record "
                             "(e.g. 'demo01,flask' or 'tutorial')")
    parser.add_argument("--demos-only", action="store_true", help="record demos only")
    parser.add_argument("--tutorials-only", action="store_true",
                        help="record tutorials only")
    parser.add_argument("--pause", type=float, default=2.0,
                        help="seconds between demo steps — screencast pace (default: 2)")
    parser.add_argument("--idle-time-limit", type=float, default=2.0,
                        help="cap recorded idle gaps for watchable playback (default: 2)")
    parser.add_argument("--upload", action="store_true",
                        help="upload each cast to asciinema.org and capture its URL")
    parser.add_argument("--visibility", default="",
                        choices=["", "public", "unlisted", "private"],
                        help="visibility for uploaded recordings")
    parser.add_argument("--title-prefix", default="Hop3 — ",
                        help="prefix for uploaded recording titles")
    parser.add_argument("--list", action="store_true",
                        help="list the items that would be recorded, then exit")
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return _self_test()

    args.only = [p for p in args.only.split(",") if p]
    args.domain = args.domain or args.host
    if args.demos_only and args.tutorials_only:
        sys.exit("--demos-only and --tutorials-only are mutually exclusive")

    items = build_items(args)
    if not items:
        sys.exit("[record_screencasts] nothing to record (no demos/tutorials found)")

    if args.list:
        for i in items:
            envtag = " ".join(f"{k}={v}" for k, v in i.env.items())
            print(f"{i.category:9} {i.name:24} {envtag + '  ' if envtag else ''}{i.command}")
        print(f"\n{len(items)} item(s).")
        return 0

    # Recording (not just listing) against a server needs a target.
    if args.backend == "ssh" and not args.host:
        sys.exit(
            "[record_screencasts] --host is required to record (the demos/tutorials "
            "run against your already-installed server).\n"
            "  e.g. --host hop3-dev.abilian.com   (or --backend docker to self-host)"
        )
    return run_and_report(items, args)


def run_and_report(items: list[Item], args: argparse.Namespace) -> int:
    """Record every item (optionally uploading), write the manifest, summarize."""
    require_tools(items)
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"[record_screencasts] {len(items)} item(s) → {args.out}")

    results: list[Result] = []
    for item in items:
        result = record(item, args.out, args.idle_time_limit)
        if args.upload:
            upload(result, visibility=args.visibility, title_prefix=args.title_prefix)
            print(f"    uploaded: {result.url}" if result.url
                  else f"    upload error: {result.error}")
        results.append(result)

    manifest = write_manifest(results, args.out)
    print(f"\n[record_screencasts] manifest: {manifest}")
    if args.upload:
        print("[record_screencasts] movie URLs (for NGI/NLNet):")
        for r in results:
            if r.url:
                print(f"  {r.item.category}:{r.item.name}  {r.url}")

    failed = [r for r in results if not (r.recorded and r.returncode == 0)]
    if failed:
        print(f"\n[record_screencasts] {len(failed)} item(s) did not record cleanly:")
        for r in failed:
            print(f"  {r.item.category}:{r.item.name} (exit {r.returncode}) {r.error}")
        return 1
    print(f"[record_screencasts] all {len(results)} item(s) recorded.")
    return 0


def _self_test() -> int:
    """Tiny offline checks for the parsing/discovery logic (no recording)."""
    assert parse_upload_url(
        "View the recording at:\n\n    https://asciinema.org/a/abc123\n"
    ) == "https://asciinema.org/a/abc123"
    assert parse_upload_url("(see https://asciinema.org/a/x9.) ") == (
        "https://asciinema.org/a/x9"
    )
    assert parse_upload_url("no url here") == ""

    demos = discover_demos(
        host="srv", backend="ssh", skip_install=True, pause=2.0, domain="srv"
    )
    tuts = discover_tutorials(host="srv", domain="dom")
    assert len({i.name for i in demos}) == len(demos), "demo names not unique"
    assert len({i.name for i in tuts}) == len(tuts), "tutorial names not unique"
    # No reinstall: demo commands must carry --skip-install and the host.
    assert all("--skip-install" in i.command and "--host srv" in i.command for i in demos)
    # Tutorials must target the server via env, not a reinstall.
    assert all(i.env.get("HOP3_API_URL") == "ssh://root@srv" for i in tuts)
    assert all(i.env.get("HOP3_TEST_DOMAIN") == "dom" for i in tuts)
    print(f"self-test OK ({len(demos)} demos, {len(tuts)} tutorials discovered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
