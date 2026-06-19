# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 60: CLI Surface Tour.

A breadth-first tour that exercises as much of the `hop3` CLI as possible in
one run, on a single throwaway app. Unlike the other demos (which each show one
feature deeply), this one is deliberately wide: it deploys a tiny app, then
walks the command surface — inspection, env, domains, scaling, addons (all four
types), backups, lifecycle, users, and the client-side commands — and prints a
coverage summary.

Design notes:
  - Every tour command runs with check=False and is recorded as ok/not-ok; the
    demo never aborts on a single command. A non-zero exit is often *expected*
    (a feature isn't installed, an empty-state listing, an auth-gated read), so
    state-dependent commands accept {0, 1}.
  - HOP3_NO_INPUT is set so the whole tour is non-interactive: `deploy` proceeds
    without the confirm prompt and destructive verbs (destroy/remove) auto-confirm.
  - It is self-cleaning: every addon (+ clone), the backup (+ restored app), and
    the throwaway user are torn down, and the app is destroyed at the end.
  - All app-scoped commands use the canonical `--app <app>` form (ADR 036 D5).

Deliberately NOT exercised (would disrupt the run, not for lack of coverage):
  - `tunnel` — holds the terminal open until Ctrl-C.
  - `auth login` / `auth logout` / `login` / `init` — re-auth or bootstrap the
    very connection the demo runs over.
  - `server` / `context` *mutation* (use/add/remove/rename) — would repoint the
    demo's own session; their read-only `list`/`show` are exercised.
  - `app create` (needs an external git repo) / `backup register` (needs a
    backup tree copied in from another instance).
  - addon `export` / `import` / `restore` — stateful dump-file round-trips;
    `dump` covers the "write a backup file" path.

PostgreSQL/MySQL/Redis/S3 and user-management degrade gracefully when the
feature isn't available on the target (service not installed / caller not admin).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 60: CLI Surface Tour"
DESCRIPTION = """
A wide tour of the hop3 CLI on one throwaway app:
  - read-only system + client-side surface (version/info/status/logs/help/…)
  - deploy, then inspect (status/ping/logs/debug/sbom/run)
  - env vars, domains, process scaling
  - addon lifecycle for ALL types (postgres/mysql/redis/s3), each gated
  - backups (create/list/show/restore/destroy) and lifecycle (restart/stop/start)
  - throwaway user-management lifecycle
Prints a coverage summary at the end. Self-cleaning.
"""

APP_NAME = "demo60"
APP_DIR = Path(__file__).parent / "app"
RESTORED_APP = "demo60-restored"
USER_NAME = "demo60user"

# Native Python app — no Docker required. Service-backed and admin-only sections
# are optional and handled gracefully, so nothing is declared mandatory.
REQUIRES: list[str] = []

_BACKUP_ID_RE = re.compile(r"\b\d{8}_\d{6}_[0-9a-f]+\b")


def _parse_backup_id(stdout: str | None) -> str | None:
    """Pull the backup id (e.g. 20260618_143022_a8f3d9) out of create output."""
    if not stdout:
        return None
    match = _BACKUP_ID_RE.search(stdout)
    return match.group(0) if match else None


def run(ctx: DemoContext) -> None:
    """Run the CLI surface tour."""
    from lib import (
        cleanup_app,
        deploy_app,
        print_header,
        print_info,
        print_success,
        print_warning,
        redeploy_app,
        set_hostname,
        test_app_via_curl,
        wait_for_app,
        wait_for_app_ready,
    )
    from lib.commands import run_hop3

    # Make every hop3 call in this demo non-interactive: deploy skips its
    # confirm prompt and destroy/remove auto-confirm. cli_env() copies
    # os.environ, and HOP3_NO_INPUT is not a dropped steering var, so this
    # propagates to every run_hop3 subprocess.
    os.environ["HOP3_NO_INPUT"] = "1"

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # (command, ok?) for the final coverage report.
    results: list[tuple[str, bool]] = []

    def cli(cmd: str, *, ok=(0,), show: bool = False, note: str = ""):
        """Run `hop3 <cmd>`, record + mark pass/fail, never raise."""
        result = run_hop3(cmd, check=False, show=show, quiet=not show)
        passed = result.returncode in ok
        results.append((cmd, passed))
        mark = "✓" if passed else "✗"
        line = f"  {mark} hop3 {cmd}"
        if note:
            line += f"   — {note}"
        (print_info if passed else print_warning)(line)
        return result

    def addon_type_tour(type_name: str, *, query: str | None, extra=()) -> None:
        """Common addon lifecycle for one type, gated on availability.

        extra: type-specific read-only verbs (e.g. settings/activity/locks/info).
        """
        name = f"demo60-{type_name}"
        clone = f"{name}-clone"
        created = cli(
            f"addon create {type_name} {name}", ok=(0, 1), note=f"needs {type_name}"
        )
        if created.returncode != 0:
            print_info(f"  {type_name} not available — skipping its addon tour.")
            return
        cli(f"addon show {name}", ok=(0, 1))
        cli(f"addon status {name}", ok=(0, 1))
        cli(f"addon exists {name}", ok=(0, 1))
        cli(f"addon credentials {name}", ok=(0, 1))
        cli(f"addon endpoint {name}", ok=(0, 1))
        cli(f"addon {type_name} credentials {name}", ok=(0, 1))
        cli(f"addon {type_name} dump {name}", ok=(0, 1))
        if query is not None:
            cli(f'addon {type_name} query {name} --command "{query}"', ok=(0, 1))
        for verb in extra:
            cli(f"addon {type_name} {verb} {name}", ok=(0, 1))
        cli(f"addon {type_name} clone {name} {clone}", ok=(0, 1))
        cli(f"addon attach {name} --app {APP_NAME} --type {type_name}", ok=(0, 1))
        cli(f"addon promote {name} --app {APP_NAME} --type {type_name}", ok=(0, 1))
        # --source loopback keeps the exposed forwarder harmless; unexpose undoes it.
        cli(f"addon expose {name} --source 127.0.0.1/32", ok=(0, 1))
        cli(f"addon unexpose {name}", ok=(0, 1))
        cli(f"addon detach {name} --app {APP_NAME} --type {type_name}", ok=(0, 1))
        cli(f"addon destroy {clone} --type {type_name}", ok=(0, 1))
        cli(f"addon destroy {name} --type {type_name}", ok=(0, 1))

    # --- 1. Read-only system surface (no app needed) ------------------------
    print_header("1. Read-only system surface")
    cli("version")
    cli("system info")
    cli("system info -v")
    cli("system status", ok=(0, 1), note="exit 1 on warnings")
    cli("system logs -n 20", ok=(0, 1))
    cli("system cleanup --dry-run", ok=(0, 1))
    cli("plugin list")
    cli("addon types")
    cli("addon list")
    cli("app list")
    cli("auth whoami", ok=(0, 1))
    cli("cert status", ok=(0, 1))
    cli("cert renew --days 1", ok=(0, 1), note="no-op unless a cert is due")
    cli("user list", ok=(0, 1))
    cli("catalog refresh", ok=(0, 1), note="network / optional")

    # --- 2. Deploy the demo app ---------------------------------------------
    print_header("2. Deploy the demo app")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app_ready(APP_NAME, timeout=30.0)
    wait_for_app(seconds=2, message="Waiting for nginx to reload...")
    test_app_via_curl(ctx, app_url, expected_content="demo60")

    # --- 3. App inspection ---------------------------------------------------
    print_header("3. App inspection")
    cli(f"app status --app {APP_NAME}")
    cli(f"app ping --app {APP_NAME}", ok=(0, 1))
    cli(f"app ping --app {APP_NAME} /health", ok=(0, 1))
    cli(f"app logs --app {APP_NAME} -n 20", ok=(0, 1))
    cli(f"app logs --app {APP_NAME} --build", ok=(0, 1))
    cli(f"app debug --app {APP_NAME}", ok=(0, 1))
    cli(f"app sbom --app {APP_NAME}", ok=(0, 1))
    cli(f"app run --app {APP_NAME} echo hello-from-run", ok=(0, 1))

    # --- 4. Environment variables (env / config alias) ----------------------
    print_header("4. Environment variables")
    cli(f"env set --app {APP_NAME} DEMO_FLAG=on LOG_LEVEL=info")
    cli(f"env show --app {APP_NAME}", show=True)
    cli(f"env show --app {APP_NAME} --sources")
    cli(f"env get --app {APP_NAME} DEMO_FLAG")
    cli(f"env live --app {APP_NAME}", ok=(0, 1))
    cli(f"env unset --app {APP_NAME} LOG_LEVEL")

    # --- 5. Domains ----------------------------------------------------------
    print_header("5. Domains")
    alt_host = f"alt-{app_hostname}"
    cli(f"domain list --app {APP_NAME}", ok=(0, 1))
    cli(f"domain add --app {APP_NAME} {alt_host}", ok=(0, 1))
    cli(f"domain list --app {APP_NAME}", ok=(0, 1))
    cli(f"domain remove --app {APP_NAME} {alt_host}", ok=(0, 1))
    cli(f"domain clear --app {APP_NAME}", ok=(0, 1))
    # Re-set the canonical hostname so the app stays reachable for later checks.
    cli(f"domain set --app {APP_NAME} {app_hostname}", ok=(0, 1))

    # --- 6. Process scaling --------------------------------------------------
    print_header("6. Process scaling (ps)")
    cli(f"ps --app {APP_NAME}", ok=(0, 1))
    cli(f"ps scale --app {APP_NAME} web=2", ok=(0, 1))
    cli(f"ps --app {APP_NAME}", ok=(0, 1))
    cli(f"ps scale --app {APP_NAME} web=1", ok=(0, 1))

    # --- 7. Addons — all four types, each gated -----------------------------
    print_header("7. Addons — PostgreSQL")
    addon_type_tour("postgres", query="SELECT 1", extra=("settings", "activity", "locks"))
    print_header("7b. Addons — MySQL")
    addon_type_tour("mysql", query="SELECT 1", extra=("settings", "activity"))
    print_header("7c. Addons — Redis")
    addon_type_tour("redis", query="DBSIZE", extra=("info", "flush"))
    print_header("7d. Addons — S3")
    addon_type_tour("s3", query=None)

    # --- 8. Backups ----------------------------------------------------------
    print_header("8. Backups")
    backup = cli(f"backup create --app {APP_NAME}", ok=(0, 1), show=True)
    cli("backup list", ok=(0, 1))
    cli(f"backup list {APP_NAME}", ok=(0, 1))
    backup_id = _parse_backup_id(backup.stdout)
    if backup_id:
        cli(f"backup show {backup_id}", ok=(0, 1))
        restored = cli(
            f"backup restore {backup_id} --target-app {RESTORED_APP}", ok=(0, 1)
        )
        if restored.returncode == 0:
            cli(f"app destroy --app {RESTORED_APP} -y", ok=(0, 1))
        cli(f"backup destroy {backup_id}", ok=(0, 1))
    else:
        print_info("No backup id parsed — skipping show/restore/destroy.")

    # --- 9. Lifecycle --------------------------------------------------------
    print_header("9. Lifecycle (restart / stop / start)")
    cli(f"app restart --app {APP_NAME}", ok=(0, 1))
    cli(f"app stop --app {APP_NAME}", ok=(0, 1))
    cli(f"app start --app {APP_NAME}", ok=(0, 1))

    # --- Tear the app down now, while the CLI connection is known-good. ------
    # The user-management section below operates over the very session the demo
    # is authenticated with (grant/revoke-admin, generate-token, remove), which
    # can perturb the CLI's own stored context/token. Cleaning up here keeps the
    # teardown reliable; the user/client-side tours don't need the app.
    print_header("Cleanup (app)")
    try:
        cleanup_app(ctx, APP_NAME, app_url)
    except Exception as exc:  # noqa: BLE001 — cleanup must never fail the tour
        print_warning(f"App cleanup hit an error (continuing the tour): {exc}")

    # --- 10. User management — throwaway account (admin only) ---------------
    print_header("10. User management (throwaway account)")
    user = cli(
        f"user add {USER_NAME} {USER_NAME}@example.com Demo60Pass123",
        ok=(0, 1),
        note="admin only",
    )
    if user.returncode == 0:
        cli(f"user show {USER_NAME}", ok=(0, 1))
        cli(f"user disable {USER_NAME}", ok=(0, 1))
        cli(f"user enable {USER_NAME}", ok=(0, 1))
        cli(f"user grant-admin {USER_NAME}", ok=(0, 1))
        cli(f"user revoke-admin {USER_NAME}", ok=(0, 1))
        cli(f"user set-password {USER_NAME} Demo60Pass456", ok=(0, 1))
        cli(f"user generate-token {USER_NAME}", ok=(0, 1))
        cli(f"user remove {USER_NAME}", ok=(0, 1))
    else:
        print_info("Could not create a throwaway user — skipping user tour.")

    # --- 11. Client-side (local) commands — read-only -----------------------
    # These run against the demo's isolated CLI home (XDG_CONFIG_HOME), so the
    # listings are safe; mutation verbs (use/add/remove) are intentionally not run.
    print_header("11. Client-side commands (read-only)")
    cli("help", ok=(0, 1))
    cli("help --all", ok=(0, 1))
    cli("aliases", ok=(0, 1))
    cli("completion --status", ok=(0, 1))
    cli("completion bash", ok=(0, 1))
    cli("context", ok=(0, 1))
    cli("context list", ok=(0, 1))
    cli("server list", ok=(0, 1))
    cli("settings show", ok=(0, 1))
    cli("settings get server", ok=(0, 1))
    cli("use", ok=(0, 1), note="show resolved default app")

    # --- Coverage report (app already torn down above) ----------------------
    print_header("CLI surface coverage")
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print_success(f"Exercised {total} commands: {passed} ok, {total - passed} non-zero.")
    failures = [cmd for cmd, ok in results if not ok]
    if failures:
        print_warning(
            "Non-zero exits (often expected — unavailable feature / empty state):"
        )
        for cmd in failures:
            print_info(f"    hop3 {cmd}")
