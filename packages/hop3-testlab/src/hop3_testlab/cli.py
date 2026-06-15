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


def main() -> None:
    parser = argparse.ArgumentParser(prog="hop3-testlab")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run the Test Lab web service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8001)
    serve.add_argument("--reload", action="store_true", help="Auto-reload (dev)")

    run = sub.add_parser("run", help="Run the test suite once under the target lease")
    run.add_argument("--target", default="docker", help="'docker' or an SSH host")
    run.add_argument(
        "--mode",
        default="nightly",
        help="smoke | ci | curated | coverage | nightly | full",
    )
    run.add_argument("--trigger", default="cli", help="provenance label for the run")
    run.add_argument(
        "--apps", nargs="*", help="specific app path(s) for a per-app build"
    )

    sub.add_parser("config", help="Show the resolved cloud config (secrets masked)")

    prune = sub.add_parser(
        "prune", help="Prune old build logs per the retention policy"
    )
    prune.add_argument(
        "--keep", type=int, default=None, help="override [retention].keep_runs"
    )

    sub.add_parser("schedule", help="Run the nightly scheduler in the foreground")

    args = parser.parse_args()
    if args.command == "serve":
        _serve(args.host, args.port, reload=args.reload)
    elif args.command == "run":
        from hop3_testlab.worker import run_once  # noqa: PLC0415

        if not run_once(
            args.target, trigger=args.trigger, mode=args.mode, apps=args.apps
        ):
            print(f"Target {args.target!r} is busy (a run holds the lease).")
            raise SystemExit(1)
    elif args.command == "config":
        _show_config()
    elif args.command == "prune":
        _prune(args.keep)
    elif args.command == "schedule":
        from hop3_testlab.cloud_config import load_schedule  # noqa: PLC0415
        from hop3_testlab.scheduler import run_blocking  # noqa: PLC0415

        s = load_schedule()
        print(f"Nightly: {s.target} {s.mode} at {s.hour:02d}:{s.minute:02d} local.")
        run_blocking()
    else:
        parser.print_help()


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
