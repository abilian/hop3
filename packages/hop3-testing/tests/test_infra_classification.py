# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Infra failures don't satisfy a negative test (audit C7).

`_run_deploy_and_verify` must classify a disk-full or a deploy-timeout as
INFRASTRUCTURE (hard fail, regardless of expects_failure), while a genuine
builder/deployer rejection stays non-infra (so it can still satisfy a negative
test). Otherwise a total outage silently turns the apps/bad apps green.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from hop3_testing.exceptions import (
    DeploymentError,
    DeployTimeoutError,
    TargetOutOfDiskError,
)
from hop3_testing.runners.deployment import DeploymentTestRunner


class _FakeTarget:
    def __init__(self, *, disk_full: bool = False) -> None:
        self._disk_full = disk_full

    def ensure_disk_headroom(self) -> None:
        if self._disk_full:
            msg = "Target out of disk: 2% free"
            raise TargetOutOfDiskError(msg)


@dataclass
class _FakeSession:
    app_name: str = "fake-app"
    last_deploy_error: str | None = None
    last_deploy_output: str | None = ""
    raises: Exception | None = None
    deployed: bool = True

    def prepare(self) -> None: ...

    def deploy(self, deploy_timeout: int) -> None:
        if self.raises is not None:
            self.last_deploy_error = str(self.raises)
            raise self.raises

    def check_deployed(self) -> bool:
        return self.deployed


def _classify(target: Any, session: Any) -> tuple[str, str | None, bool]:
    runner = DeploymentTestRunner(target=cast("Any", target), cleanup=True)
    return runner._run_deploy_and_verify(
        cast("Any", None), cast("Any", session), 0.0, []
    )


def test_disk_full_is_infra():
    _logs, error, infra = _classify(_FakeTarget(disk_full=True), _FakeSession())
    assert infra is True
    assert error is not None
    assert "out of disk" in error


def test_timeout_is_infra():
    session = _FakeSession(
        raises=DeployTimeoutError("Deploy timed out after 30 minutes")
    )
    _logs, error, infra = _classify(_FakeTarget(), session)
    assert infra is True
    assert error is not None
    assert "Deploy failed" in error


def test_builder_rejection_is_not_infra():
    # A genuine rejection must STILL be able to satisfy a negative test.
    session = _FakeSession(
        raises=DeploymentError("Exit code: 8 | poetry could not resolve deps")
    )
    _logs, error, infra = _classify(_FakeTarget(), session)
    assert infra is False
    assert error is not None
    assert "Deploy failed" in error


def test_success_is_not_infra():
    _logs, error, infra = _classify(_FakeTarget(), _FakeSession())
    assert error is None
    assert infra is False
