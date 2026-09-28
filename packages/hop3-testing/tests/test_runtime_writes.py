# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
What the running app wrote into `src/`, and whether a redeploy keeps it working.

Every deploy replaces `src/`, so anything the app writes there is deleted by
the next one. A test that deploys once never sees it: Nextcloud's user files,
WordPress uploads, Forgejo's repositories were all kept there. The runner
lists what the app wrote after its workers started, and redeploys the
unchanged source to run every validation again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from hop3_testing.catalog.models import (
    DeploymentConfig,
    Priority,
    TestDefinition,
    TestRequirements,
    Tier,
)
from hop3_testing.exceptions import DeploymentError
from hop3_testing.runners import deployment as deployment_module
from hop3_testing.runners.deployment import (
    _NO_MARKER,
    _NO_WORKERS,
    DeploymentTestRunner,
    _runtime_writes_script,
)
from hop3_testing.targets.constants import WORKERS_STARTED_MARKER

from hop3.run.spawn import AppLauncher

if TYPE_CHECKING:
    from hop3_testing.runners.base import ValidationResult


class _Target:
    """Answers the probe the way a server would, and records it."""

    def __init__(self, stdout: str = "", exit_code: int = 0) -> None:
        self.stdout, self.exit_code = stdout, exit_code
        self.commands: list[Any] = []

    def exec_run(self, cmd: Any) -> tuple[int, str, str]:
        self.commands.append(cmd)
        return self.exit_code, self.stdout, "find: permission denied"

    def ensure_disk_headroom(self) -> None:
        pass


class _Session:
    app_name = "wiki-1"
    last_deploy_error = "Exit code: 1 | occ: Nextcloud is already installed"
    last_deploy_output = ""

    def __init__(self, redeploy_fails: bool = False) -> None:
        self.deploys = 0
        self.redeploy_fails = redeploy_fails

    def deploy(self, deploy_timeout: int) -> None:
        self.deploys += 1
        if self.redeploy_fails:
            raise DeploymentError(self.last_deploy_error)


def _check(stdout: str, exit_code: int = 0) -> tuple[str | None, ValidationResult]:
    runner = DeploymentTestRunner(target=cast("Any", _Target(stdout, exit_code)))
    results: list[ValidationResult] = []
    error = runner._check_runtime_writes(cast("Any", _Session()), results)
    return error, results[-1]


def test_files_the_app_wrote_into_src_fail_the_test() -> None:
    error, result = _check(
        "data/nextcloud.log\ndata/appdata/x.css\nstorage/framework/views/a.php\n"
    )
    assert error is not None
    assert not result.passed
    assert "wrote 3 file(s) into src/" in error
    assert "[[volumes]]" in error
    # Grouped by directory, two levels down at most, so the fix is readable.
    assert "  data/ (1 file)\n  data/appdata/ (1 file)\n" in error
    assert "  storage/framework/ (1 file)" in error


def test_nothing_written_passes() -> None:
    error, result = _check("")
    assert error is None
    assert result.passed


def test_an_app_without_workers_has_nothing_to_check() -> None:
    error, result = _check(f"{_NO_WORKERS}\n")
    assert error is None
    assert result.message == "No worker runs from src/"


def test_a_server_that_records_no_start_fails_loud() -> None:
    # An older server behind --reuse: the check cannot tell the app's writes
    # from the deploy's, and a pass would claim what it never measured.
    error, _ = _check(f"{_NO_MARKER}\n")
    assert error is not None
    assert "predates this harness" in error


def test_a_probe_that_cannot_run_fails_loud() -> None:
    error, _ = _check("", exit_code=1)
    assert error is not None
    assert "exit 1" in error


def test_the_probe_reads_the_marker_the_server_writes() -> None:
    assert WORKERS_STARTED_MARKER == AppLauncher.WORKERS_STARTED_MARKER
    script = _runtime_writes_script("wiki-1")
    assert f"/home/hop3/apps/wiki-1/{WORKERS_STARTED_MARKER}" in script
    # A volume is a link: what lands in one must not be listed.
    assert "find -L" not in script
    # A socket is made again at every start: never state, never listed.
    assert "! -type s" in script


def test_a_failed_redeploy_fails_the_test() -> None:
    runner = DeploymentTestRunner(target=cast("Any", _Target()))
    session = _Session(redeploy_fails=True)
    results: list[ValidationResult] = []

    error = runner._redeploy_and_revalidate(
        cast("Any", None), cast("Any", session), cast("Any", None), results
    )

    assert error is not None
    assert "Redeploying the unchanged source failed" in error
    assert "already installed" in error
    assert results[-1].validation_type == "redeploy"
    assert not results[-1].passed


class _WorkingSession(_Session):
    def __init__(self, **_kwargs: Any) -> None:
        super().__init__()

    def prepare(self) -> None:
        pass

    def check_deployed(self) -> bool:
        return True

    def cleanup(self) -> None:
        pass


def _run(tmp_path, monkeypatch, *, redeploy: bool) -> _WorkingSession:
    sessions: list[_WorkingSession] = []

    def _factory(**kwargs: Any) -> _WorkingSession:
        sessions.append(_WorkingSession(**kwargs))
        return sessions[-1]

    monkeypatch.setattr(deployment_module, "DeploymentSession", _factory)
    monkeypatch.setattr(
        DeploymentTestRunner, "_run_http_validations", lambda *a, **k: None
    )
    runner = DeploymentTestRunner(
        target=cast("Any", _Target()), cleanup=True, redeploy=redeploy
    )
    test = TestDefinition(
        name="wiki",
        tier=Tier.FAST,
        priority=Priority.P0,
        requirements=TestRequirements(),
        deployment=DeploymentConfig(path="."),
        source_path=tmp_path / "test.toml",
    )
    result = runner.run(test)
    assert result.passed, result.error
    return sessions[0]


def test_an_app_is_redeployed_by_default(tmp_path, monkeypatch) -> None:
    assert _run(tmp_path, monkeypatch, redeploy=True).deploys == 2


def test_no_redeploy_deploys_once(tmp_path, monkeypatch) -> None:
    assert _run(tmp_path, monkeypatch, redeploy=False).deploys == 1
