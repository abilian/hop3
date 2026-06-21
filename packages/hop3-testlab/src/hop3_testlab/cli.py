# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test Lab CLI entry point.

``hop3-testlab serve`` boots the web service via Granian (same process model as
hop3-server). ``run`` (the nightly/worker driver) and ``db:*`` commands are
added in later milestones.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hop3-testlab")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run the Test Lab web service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8001)
    serve.add_argument("--reload", action="store_true", help="Auto-reload (dev)")

    # `run <mode> [selector]`: positional mode (provenance label + suite when no
    # selector), optional selector (a glob over app names — quote it so the shell
    # doesn't expand it locally; it resolves server-side, v2 spec §1/§A).
    run = sub.add_parser("run", help="Run a test suite once under the target lease")
    run.add_argument(
        "mode",
        nargs="?",
        default="nightly",
        help="smoke | ci | curated | coverage | nightly | full",
    )
    run.add_argument(
        "selector",
        nargs="?",
        default=None,
        help="glob over app names, e.g. 'apps/test-apps-procfile/*' (quote it)",
    )
    run.add_argument("--target", default="docker", help="'docker' or an SSH host")
    run.add_argument("--trigger", default="cli", help="provenance label for the run")
    run.add_argument(
        "--source-url",
        default=None,
        help="git URL/path for the apps (default: local repo)",
    )
    run.add_argument(
        "--source-name", default="main-repo", help="label for the app source"
    )
    run.add_argument(
        "--source-ref",
        default=None,
        help="git ref to fetch the apps at (branch/tag/sha) — enables composition",
    )
    run.add_argument(
        "--platform-ref",
        default=None,
        help="hop3 ref to install on the target (--branch); default: engine default",
    )

    sub.add_parser("config", help="Show the resolved cloud config (secrets masked)")

    prune = sub.add_parser(
        "prune", help="Prune old build logs per the retention policy"
    )
    prune.add_argument(
        "--keep", type=int, default=None, help="override [retention].keep_runs"
    )

    sub.add_parser("schedule", help="Run the nightly scheduler in the foreground")

    logs = sub.add_parser("logs", help="Show the latest build log (builder output)")
    logs.add_argument(
        "-f", "--follow", action="store_true", help="follow live (tail -f)"
    )
    logs.add_argument("-n", "--lines", type=int, default=40, help="lines to show")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "serve":
        _serve(args.host, args.port, reload=args.reload)
    elif args.command == "run":
        _run(args)
    elif args.command == "config":
        _show_config()
    elif args.command == "prune":
        _prune(args.keep)
    elif args.command == "logs":
        _logs(follow=args.follow, lines=args.lines)
    elif args.command == "schedule":
        from hop3_testlab.cloud_config import load_schedule  # noqa: PLC0415
        from hop3_testlab.scheduler import run_blocking  # noqa: PLC0415

        s = load_schedule()
        print(f"Nightly: {s.target} {s.mode} at {s.hour:02d}:{s.minute:02d} local.")
        run_blocking()
    else:
        parser.print_help()


def _run(args: argparse.Namespace) -> None:
    """Dispatch the ``run`` subcommand: a composition run (``--source-ref``) or a
    local run (the selector, if any, resolved against the local checkout)."""
    from hop3_testlab.worker import RunSpec, run_once  # noqa: PLC0415

    source = None
    apps = None
    selector = None
    if args.source_ref:
        from hop3_testing.targets.helpers import find_project_root  # noqa: PLC0415

        from hop3_testlab.sources import Source  # noqa: PLC0415

        url = args.source_url or str(find_project_root())
        source = Source(args.source_name, url)
        selector = args.selector  # resolved server-side against the fetched workspace
    elif args.selector:
        # No source -> a local run: resolve the selector against the local checkout
        # now (fail loud if it matches nothing rather than silently run the suite).
        from hop3_testing.targets.helpers import find_project_root  # noqa: PLC0415

        from hop3_testlab.catalog import resolve_selector  # noqa: PLC0415

        apps = resolve_selector(find_project_root(), args.selector)
        if not apps:
            print(f"No apps match selector {args.selector!r}.")
            raise SystemExit(1)

    spec = RunSpec(
        source=source,
        source_ref=args.source_ref,
        platform_ref=args.platform_ref,
        selector=selector,
        apps=apps,
    )
    if run_once(args.target, trigger=args.trigger, mode=args.mode, spec=spec):
        return
    print(f"Target {args.target!r} is busy (a run holds the lease).")
    raise SystemExit(1)


LOG_DIR = Path.home() / ".hop3" / "testlab-logs"


def _latest_log(log_dir: Path) -> Path | None:
    """The most-recently-written build log in ``log_dir`` (or None)."""
    logs = list(log_dir.glob("*.log")) if log_dir.is_dir() else []
    return max(logs, key=lambda p: p.stat().st_mtime) if logs else None


def _logs(*, follow: bool, lines: int) -> None:
    """Show the latest build log (the builder's teed output) on the console.

    A UI-triggered build runs detached and tees its output here, so its progress
    never reaches the console it was launched from; this surfaces it (``-f`` to
    watch a run live).
    """
    import subprocess  # noqa: PLC0415

    latest = _latest_log(LOG_DIR)
    if latest is None:
        print(f"No build logs yet (looked in {LOG_DIR}).")
        return
    print(f"# {latest}\n")
    cmd = ["tail", "-n", str(lines), *(["-f"] if follow else []), str(latest)]
    subprocess.run(cmd, check=False)


def _prune(keep: int | None) -> None:
    from hop3_testing.results import ResultStore  # noqa: PLC0415

    from hop3_testlab.cloud_config import load_retention  # noqa: PLC0415
    from hop3_testlab.config import TestlabConfig  # noqa: PLC0415

    keep_runs = keep if keep is not None else load_retention()
    store = ResultStore(db_path=TestlabConfig.get_instance().DB_PATH)
    deleted = store.prune_build_logs(keep_runs)
    print(f"Pruned {deleted} build-log rows (kept the most recent {keep_runs} runs).")


def _show_config() -> None:
    from hop3_testlab.cloud_config import load_cloud_config  # noqa: PLC0415

    cfg = load_cloud_config()
    token = cfg.hetzner_token
    masked = (
        f"{token[:4]}…{token[-4:]}" if len(token) >= 8 else ("set" if token else "—")
    )
    print(f"hetzner.api_token : {masked}")
    print(f"hetzner.server_id : {cfg.hetzner_server_id or '—'}")
    print(f"hetzner.image     : {cfg.hetzner_image}")
    print(f"ssh.key_path      : {cfg.ssh_key_path or '—'}")
    print(f"complete          : {cfg.is_complete}")


def _serve(host: str, port: int, *, reload: bool = False) -> None:
    import granian  # noqa: PLC0415
    from granian.constants import Interfaces  # noqa: PLC0415

    granian.Granian(
        target="hop3_testlab.web.asgi:create_app",
        factory=True,
        address=host,
        port=port,
        interface=Interfaces.ASGI,
        reload=reload,
    ).serve()
