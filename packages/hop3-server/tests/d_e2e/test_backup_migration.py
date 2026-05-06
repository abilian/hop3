# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for cross-instance backup migration.

Validates the disaster-recovery / server-migration / clone-to-staging
path: a backup taken on instance A reconstructs the app correctly on a
fresh instance B. Single-instance round-trips are covered in
`test_backup.py`; this file covers what those can't catch — issues that
only show up across instances (different `HOP3_SECRET_KEY`, different
addon credentials, fresh nginx state, fresh database).

See `local-notes/plans/backup-plans.md` for the design + milestones.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from hop3_testing.apps import DeploymentSession
from hop3_testing.apps.catalog import AppSource

from .conftest import (
    BACKUP_DIR_IN_CONTAINER,
    create_flask_app,
    extract_backup_id,
    transfer_backup_dir,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class HttpResponse:
    """Captured HTTP response for equivalence comparison across instances."""

    status: int
    body: str


def _fetch_app_response(
    target: Any,
    app_name: str,
    path: str = "/",
    *,
    timeout_seconds: float = 30.0,
) -> HttpResponse:
    """Fetch an HTTP response from `app_name` running on `target`.

    Reads the app's bound port from its uwsgi config inside the container
    (independent of whether a `DeploymentSession` exists for this target),
    then curls 127.0.0.1:<port><path> from *inside* the container — the
    same approach `DeploymentSession._test_http_direct` uses, just
    without the session-state coupling.

    Hop3 uwsgi configs are emitted at
    ``/home/hop3/uwsgi-enabled/<app>_<kind>.<w>.ini`` with workers
    1-indexed (see ``hop3.run.spawn``). We glob for the first ``_web``
    worker — sufficient for single-worker test apps and the right one
    to query for an HTTP equivalence check anyway.

    Polls until the worker ini exists (it's emitted lazily after
    deploy / restart) and the worker accepts a connection, with
    ``timeout_seconds`` total budget.

    Args:
        target: a ``DockerTarget``
        app_name: the app to fetch from
        path: URL path; defaults to ``/``
        timeout_seconds: total budget waiting for the worker to come up.

    Returns:
        ``HttpResponse(status, body)``.

    Raises:
        RuntimeError if no web-worker ini appears within the timeout, or
        if the worker exists but never serves a request.
    """
    container = target._container_helper.container
    glob = f"/home/hop3/uwsgi-enabled/{app_name}_web.*.ini"
    deadline = time.monotonic() + timeout_seconds
    last_diagnostic = ""

    while time.monotonic() < deadline:
        # `ls -1` to get one path per line; use `sh -c` so the glob is
        # expanded by the shell rather than passed literally.
        ls = container.exec_run(["sh", "-c", f"ls -1 {glob} 2>/dev/null"])
        candidates = [
            line.strip() for line in ls.output.decode().splitlines() if line.strip()
        ]
        if not candidates:
            diagnostic = container.exec_run(["ls", "-1", "/home/hop3/uwsgi-enabled/"])
            last_diagnostic = (
                f"uwsgi-enabled/ contents:\n{diagnostic.output.decode()}"
            )
            time.sleep(1)
            continue

        ini_path = candidates[0]
        cat = container.exec_run(["cat", ini_path])
        if cat.exit_code != 0:
            last_diagnostic = f"Could not read {ini_path}: {cat.output!r}"
            time.sleep(1)
            continue

        port = _parse_uwsgi_port(cat.output.decode())
        if port is None:
            last_diagnostic = (
                f"No PORT env in {ini_path}:\n{cat.output.decode()}"
            )
            time.sleep(1)
            continue

        # Worker exists. Try the curl (worker may still be starting).
        curl_result = container.exec_run([
            "curl", "-s", "-o", "-", "-w", "\n%{http_code}",
            "--max-time", "3",
            f"http://127.0.0.1:{port}{path}",
        ])
        if curl_result.exit_code == 0:
            output = curl_result.output.decode()
            body, _sep, status = output.rpartition("\n")
            try:
                status_code = int(status.strip())
            except ValueError:
                last_diagnostic = f"Non-numeric status from curl: {output!r}"
                time.sleep(1)
                continue
            # Worker process still warming up returns 502/503/504 via
            # the local socket; retry briefly on those.
            if status_code in {502, 503, 504}:
                last_diagnostic = f"Worker not ready: HTTP {status_code}"
                time.sleep(1)
                continue
            return HttpResponse(status=status_code, body=body)

        last_diagnostic = f"curl failed: {curl_result.output!r}"
        time.sleep(1)

    msg = (
        f"App '{app_name}' did not serve {path} within "
        f"{timeout_seconds}s. Last diagnostic:\n{last_diagnostic}"
    )
    raise RuntimeError(msg)


_UWSGI_PORT_RE = re.compile(r"^\s*env\s*=\s*PORT=(\d+)\s*$", re.MULTILINE)


def _parse_uwsgi_port(ini_content: str) -> int | None:
    """Extract the bound port from a Hop3 uwsgi worker ini.

    Hop3 doesn't put workers behind uWSGI's own HTTP socket — instead
    each worker runs as an `attach-daemon` shell command with the bound
    port exposed via `env = PORT=NNNN`. The flask/gunicorn/etc. process
    listens on 127.0.0.1:$PORT and nginx (or our test curl) hits it
    there.
    """
    match = _UWSGI_PORT_RE.search(ini_content)
    return int(match.group(1)) if match else None


@pytest.mark.e2e
class TestBackupMigrationE2E:
    """Cross-instance backup → restore migration.

    Uses the `hop3_container_pair` fixture (two independent
    ``DockerTarget`` instances from the pre-built ``hop3-e2e:test``
    image). Class-scoped so the pair is reused across the test methods
    in this class.
    """

    def test_pair_fixture_smoke(self, hop3_container_pair):
        """M1 smoke test: both halves of the pair are healthy and addressable.

        Validates that `hop3_container_pair` brings up two distinct
        ``DockerTarget`` instances, each with its own ports, and that
        ``run_command`` works against both. This is the precondition
        for every other test in this file.
        """
        a, b = hop3_container_pair

        # Two distinct targets (different api_urls, different ssh_ports).
        assert a.info.api_url != b.info.api_url
        assert a.info.ssh_port != b.info.ssh_port

        # CLI works against both targets via the HTTP+token path
        # (DockerTarget.run_command bypasses SSH tunnels).
        a_apps = a.run_command("apps")
        assert a_apps.success, f"hop3 apps failed on A: stderr={a_apps.stderr}"

        b_apps = b.run_command("apps")
        assert b_apps.success, f"hop3 apps failed on B: stderr={b_apps.stderr}"

    def test_transfer_backup_dir_helper(self, hop3_container_pair):
        """M1 smoke test: `transfer_backup_dir` moves a directory tree A→B.

        Doesn't exercise the backup machinery yet — just plants a
        sentinel directory under Hop3's backup root on A and confirms it
        lands at the same path on B with content intact.
        """
        a, b = hop3_container_pair
        sentinel_app = "smoketest-app"
        backup_id = "fake-backup-id-0001"
        sentinel_content = b"smoke-test-content\n"

        a_container = a._container_helper.container
        a_path = f"{BACKUP_DIR_IN_CONTAINER}/{sentinel_app}/{backup_id}"
        a_container.exec_run(["mkdir", "-p", a_path], user="root")
        a_container.exec_run(
            ["sh", "-c", f"echo -n '{sentinel_content.decode()}' > {a_path}/marker.txt"],
            user="root",
        )
        # Leave the backup root hop3-owned so a later test in this class
        # (which runs `hop3 backup create` as the hop3 user) doesn't fail
        # with permission-denied on the parent path. Class-scoped
        # `hop3_container_pair` shares the containers across tests.
        a_container.exec_run(
            ["chown", "-R", "hop3:hop3", "/home/hop3/backups"], user="root"
        )

        transfer_backup_dir(a, b, sentinel_app)

        b_container = b._container_helper.container
        b_container.exec_run(
            ["chown", "-R", "hop3:hop3", "/home/hop3/backups"], user="root"
        )
        result = b_container.exec_run(["cat", f"{a_path}/marker.txt"])
        assert result.exit_code == 0, (
            f"marker file not found on B at {a_path}/marker.txt: {result.output!r}"
        )
        assert result.output == sentinel_content, (
            f"content mismatch: expected {sentinel_content!r}, got {result.output!r}"
        )

    def test_migrate_simple_app(self, hop3_container_pair, tmp_path: Path):
        """M2 happy path: deploy on A, backup, transfer, restore on B, verify equivalent.

        Three equivalence layers, in increasing strictness:
          1. App registered on B (`hop3 apps` includes the name)
          2. Env vars preserved (`hop3 config show --show-secrets`)
          3. HTTP body byte-equivalent (golden response from A == response from B)

        ``DeploymentSession`` rewrites the app name with a timestamp suffix
        (e.g. ``migrate-app`` → ``migrate-app-<unix_ts>``) to avoid
        collisions across runs. We therefore use ``session.app_name``
        everywhere the deployed name matters — including on B, where the
        restored app keeps the same name as on A.
        """
        a, b = hop3_container_pair

        # 1. Deploy on A and capture the golden HTTP response.
        app_dir = create_flask_app(tmp_path, "migrate-app", "Hello from migrate-app!")
        with DeploymentSession(AppSource(name="migrate-app", path=app_dir), a) as session:
            session.deploy()
            assert session.check_deployed(), "App not properly deployed on A"

            deployed_name = session.app_name  # timestamped variant

            golden = _fetch_app_response(a, deployed_name, "/")
            assert golden.status == 200, (
                f"Expected golden 200 from A, got {golden.status}; body={golden.body!r}"
            )

            # 2. Distinguishing env vars (we'll re-read them on B post-restore).
            for kv in ("MARKER=A1B2C3", "DEBUG=true"):
                res = a.run_command("config", "set", deployed_name, kv)
                assert res.success, f"failed to set {kv} on A: {res.stderr}"

            # 3. Backup on A.
            res = a.run_command("backup", "create", deployed_name)
            assert res.success, f"backup create failed on A: {res.stderr}"
            backup_id = extract_backup_id(res.stdout)
            assert backup_id, f"could not extract backup_id from: {res.stdout!r}"

        # 4. Transport the entire backup tree A → B. The DeploymentSession
        # exits at this point, destroying the app on A — but the backup
        # files under /home/hop3/backups/apps/<deployed_name>/ survive.
        transfer_backup_dir(a, b, deployed_name)

        # 5. Register the transferred backup in B's database. This is
        # what `restore_backup` looks up — without the DB row,
        # filesystem-only transport is invisible to the restore command.
        # Mirrors what an operator does after `scp`-ing a backup dir.
        register_path = f"{BACKUP_DIR_IN_CONTAINER}/{deployed_name}/{backup_id}"
        res = b.run_command("backup", "register", register_path)
        assert res.success, f"backup register failed on B: {res.stderr}"
        assert backup_id in res.stdout, (
            f"register did not echo backup_id: {res.stdout!r}"
        )

        # 6. Restore on B. As of this PR, `backup restore` invokes the
        # build+spawn pipeline at the end, so the app is running on B
        # immediately after this command returns — no separate restart
        # step needed. (Before, the operator had to manually rebuild;
        # the migration test surfaced that as broken UX.)
        res = b.run_command("backup", "restore", backup_id)
        if not res.success:
            # Pull diagnostics from B's server log on failure to surface
            # the actual deploy-pipeline error (the BackupRestoreCmd
            # error wrapping flattens the underlying exception message).
            log_dump = b._container_helper.container.exec_run(
                ["tail", "-n", "100", "/var/log/supervisor/hop3-server.log"]
            )
            err_dump = b._container_helper.container.exec_run(
                ["tail", "-n", "100", "/var/log/supervisor/hop3-server_err.log"]
            )
            pytest.fail(
                f"restore failed on B:\n"
                f"  stderr: {res.stderr}\n"
                f"  hop3-server log:\n{log_dump.output.decode()}\n"
                f"  hop3-server err:\n{err_dump.output.decode()}"
            )
        assert "Restore completed successfully!" in res.stdout, (
            f"Restore output unexpected: {res.stdout!r}"
        )

        # 6a. App registered on B.
        b_apps = b.run_command("apps")
        assert b_apps.success
        assert deployed_name in b_apps.stdout, (
            f"'{deployed_name}' not in B's app list:\n{b_apps.stdout}"
        )

        # 6b. Env vars preserved on B (the distinguishing markers).
        # `config show` renders a Rich table; assert both the key and
        # the value appear in the output rather than coupling on the
        # exact `KEY=VALUE` form.
        cfg = b.run_command("config", "show", deployed_name, "--show-secrets")
        assert cfg.success, f"config show failed on B: {cfg.stderr}"
        for key, value in (("MARKER", "A1B2C3"), ("DEBUG", "true")):
            assert key in cfg.stdout, (
                f"env-var key {key!r} missing on B: {cfg.stdout!r}"
            )
            assert value in cfg.stdout, (
                f"env-var value for {key} ({value!r}) missing on B: {cfg.stdout!r}"
            )

        # 6c. HTTP body equivalent on B.
        b_response = _fetch_app_response(b, deployed_name, "/")
        assert b_response.status == golden.status, (
            f"status mismatch: A={golden.status}, B={b_response.status}"
        )
        assert b_response.body == golden.body, (
            f"body mismatch: A={golden.body!r}, B={b_response.body!r}"
        )

    # --- M3 negative paths ----------------------------------------------

    def test_restore_when_app_name_collides_on_b(
        self, hop3_container_pair, tmp_path: Path
    ):
        """Name collision on B: restore silently overwrites the existing app.

        When B already has an app with the backup's app_name, ``backup
        restore`` (without ``--target-app``) replaces B's version with
        A's. This locks in current behaviour. The friendlier UX
        (refuse without an explicit ``--force``) is captured in
        ``release-0.6-targets.md`` §4.1 — pulling it forward isn't part
        of M3.3.
        """
        a, b = hop3_container_pair
        name = "collision-test"

        # 1. Deploy on A with distinguishing body, capture backup, exit
        # (A's app destroyed at session exit; backup files survive).
        # Distinct local dir names (`-a-src`, `-b-src`) — `create_flask_app`
        # mkdirs `<tmp_path>/<name>` without parents, so the local dir
        # name has to be unique even though the deployed app_name is shared.
        src_a = create_flask_app(tmp_path, f"{name}-a-src", "from A")
        with DeploymentSession(
            AppSource(name=name, path=src_a), a, app_name=name
        ) as session_a:
            session_a.deploy()
            res = a.run_command("backup", "create", name)
            assert res.success, f"backup create failed on A: {res.stderr}"
            backup_id = extract_backup_id(res.stdout)
            assert backup_id

        # 2. Deploy a *different* app on B under the same name.
        # 3. Inside the same with-block, migrate from A and assert
        # overwrite. (Session exit at the end of the block destroys
        # whichever variant of the app is alive then — a fine cleanup.)
        src_b = create_flask_app(tmp_path, f"{name}-b-src", "from B")
        with DeploymentSession(
            AppSource(name=name, path=src_b), b, app_name=name
        ) as session_b:
            session_b.deploy()

            # Pre-restore: B serves its own version.
            before = _fetch_app_response(b, name, "/")
            assert before.body == "from B", (
                f"unexpected pre-restore body on B: {before.body!r}"
            )

            # Migrate.
            transfer_backup_dir(a, b, name)
            register_path = f"{BACKUP_DIR_IN_CONTAINER}/{name}/{backup_id}"
            res = b.run_command("backup", "register", register_path)
            assert res.success, f"register failed on B: {res.stderr}"

            res = b.run_command("backup", "restore", backup_id)
            assert res.success, f"restore failed on B: {res.stderr}"

            # Post-restore: B's app now reflects A's content (silent
            # overwrite). If/when the 0.6 refusal-by-default UX lands,
            # this assertion flips to expect a clear error instead.
            after = _fetch_app_response(b, name, "/")
            assert after.body == "from A", (
                f"expected overwrite to A's body, got {after.body!r}"
            )

    def test_migrate_via_target_app(self, hop3_container_pair, tmp_path: Path):
        """``--target-app`` produces a separate app on B alongside any pre-existing one.

        Operator workflow: B already runs `same-name` for unrelated
        reasons. We want to bring in A's backup as a *clone* without
        clobbering B's existing app. Equivalent to "restore to a new
        name" — the same code path that the existing
        `test_restore_to_different_app_name` exercises within a single
        instance, here verified across instances.
        """
        a, b = hop3_container_pair
        name = "clone-source"
        clone_name = "clone-target"

        # Backup on A.
        src_a = create_flask_app(tmp_path, f"{name}-a-src", "source content")
        with DeploymentSession(
            AppSource(name=name, path=src_a), a, app_name=name
        ) as session_a:
            session_a.deploy()
            res = a.run_command("backup", "create", name)
            assert res.success
            backup_id = extract_backup_id(res.stdout)

        # On B: pre-existing app under the *original* name with
        # different content.
        src_b = create_flask_app(tmp_path, f"{name}-b-src", "untouched B content")
        with DeploymentSession(
            AppSource(name=name, path=src_b), b, app_name=name
        ) as session_b:
            session_b.deploy()

            # Migrate as a clone, NOT overwriting B's `name` app.
            transfer_backup_dir(a, b, name)
            register_path = f"{BACKUP_DIR_IN_CONTAINER}/{name}/{backup_id}"
            res = b.run_command("backup", "register", register_path)
            assert res.success

            res = b.run_command(
                "backup", "restore", backup_id, "--target-app", clone_name
            )
            assert res.success, f"clone restore failed: {res.stderr}"
            assert clone_name in res.stdout, (
                f"clone name not echoed: {res.stdout!r}"
            )

            # Both apps exist on B.
            apps_list = b.run_command("apps").stdout
            assert name in apps_list, f"{name!r} missing on B: {apps_list}"
            assert clone_name in apps_list, (
                f"{clone_name!r} missing on B: {apps_list}"
            )

            # Original app on B unchanged.
            original = _fetch_app_response(b, name, "/")
            assert original.body == "untouched B content", (
                f"original app on B was modified: {original.body!r}"
            )

            # Cloned app reflects A's content.
            clone = _fetch_app_response(b, clone_name, "/")
            assert clone.body == "source content", (
                f"clone body wrong: {clone.body!r}"
            )

            # Best-effort cleanup of the clone (the session destroys
            # the original at __exit__; the clone is a separate app).
            b.run_command("app", "destroy", clone_name)

    def test_register_refuses_corrupted_backup(self, hop3_container_pair, tmp_path: Path):
        """`backup register` rejects a backup directory missing its manifest.

        Migration-by-filesystem only works if the manifest is intact.
        Register catches the corruption explicitly so the operator gets
        a useful error rather than letting `restore` fail later with a
        less actionable message.
        """
        a, b = hop3_container_pair
        name = "corrupt-test"

        # Create a real backup on A, then transfer + corrupt on B.
        src = create_flask_app(tmp_path, name, "doesn't matter")
        with DeploymentSession(
            AppSource(name=name, path=src), a, app_name=name
        ) as session_a:
            session_a.deploy()
            res = a.run_command("backup", "create", name)
            assert res.success
            backup_id = extract_backup_id(res.stdout)

        transfer_backup_dir(a, b, name)

        # Corrupt: delete metadata.json from B's copy.
        b_container = b._container_helper.container
        metadata_path = (
            f"{BACKUP_DIR_IN_CONTAINER}/{name}/{backup_id}/metadata.json"
        )
        rm_result = b_container.exec_run(["rm", metadata_path], user="root")
        assert rm_result.exit_code == 0, (
            f"could not remove metadata for corruption test: {rm_result.output!r}"
        )

        # Register should refuse with a clear message.
        register_path = f"{BACKUP_DIR_IN_CONTAINER}/{name}/{backup_id}"
        res = b.run_command("backup", "register", register_path)
        assert not res.success, (
            f"register unexpectedly succeeded on a corrupted backup: {res.stdout!r}"
        )
        # The operator-facing error should mention the missing manifest.
        combined = (res.stdout + res.stderr).lower()
        assert "manifest" in combined or "metadata.json" in combined, (
            f"error didn't reference the missing manifest: "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )
