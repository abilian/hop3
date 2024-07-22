# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

# ruff: noqa: E402

"""
Hop3 test runner.
"""

from __future__ import annotations

import argparse
import sys
from multiprocessing.pool import Pool
from pathlib import Path

from cleez.colors import green, red
from devtools import debug

from hop3.util.console import Abort

from .base import TestSession

# from .common import update_agent


def main() -> None:
    parser = argparse.ArgumentParser("Run end-to-end tests")

    parser.add_argument(
        "-k",
        "--keep",
        action="store_true",
        help="Keep apps alive",
    )
    parser.add_argument(
        "-p",
        "--parallel",
        action="store_true",
        help="Run in parallel (not working)",
    )
    parser.add_argument(
        "-d",
        "--directory",
        help="Directory to look for apps",
    )
    parser.add_argument(
        "-a",
        "--app",
        help="App to test",
    )

    parser.add_argument(
        "--ff",
        action="store_true",
        help="Fail fast",
    )

    args = parser.parse_args()

    apps = get_apps(args)
    apps = sorted(apps)

    if not apps:
        raise Abort("No apps found.")

    # update_agent()

    config = {
        "keep": args.keep,
        "ff": args.ff,
    }

    if args.parallel:
        # Not working
        run_tests_parallel(apps, config)
    else:
        run_tests(apps, config)


def run_tests_parallel(apps, config):
    # Not working
    def run(app):
        session = TestSession(app, config)
        return session.run()

    with Pool(4) as pool:
        results = pool.map(run, apps)
    debug(zip(apps, results))


def run_tests(apps, config):
    test_results = []
    status = 0
    for app in sorted(apps):
        print(green(f"Testing {app}"))
        session = TestSession(app, config)
        result = session.run()
        if result == "error":
            status = 1
            if config["ff"]:
                print(f"Fail fast: stopping tests after error on app {app}")
                sys.exit(1)
        test_results.append((app, result))

    print_results(test_results)
    sys.exit(status)


def get_apps(args) -> list | list[Path]:
    print(args)
    if args.directory:
        directory = Path(args.directory)
    else:
        directory = Path("apps", "test-apps")

    if args.app:
        app = Path(args.app)
        if app.is_dir():
            return [app]
        return [directory / app]

    apps = filter(lambda x: x.is_dir(), directory.iterdir())
    apps = filter(lambda x: not x.name.startswith("xxx-"), apps)
    return apps


def print_results(test_results) -> None:
    print("\n\n\nTest results:")
    for app, status in test_results:
        match status:
            case "success":
                print(green(f"{app}: {status}"))
            case "error":
                print(red(f"{app}: {status}"))


if __name__ == "__main__":
    main()
