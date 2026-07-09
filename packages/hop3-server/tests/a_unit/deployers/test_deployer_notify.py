# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Deploy-failure operator notification — the single choke point (ADR 054).

`do_deploy` wraps the orchestration so a failed deploy alerts the operator
through the email backend, best-effort, without ever masking the deploy error.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hop3.deployers import deployer


class _App:
    name = "myapp"
    id = 1


def test_failure_notifies_operator():
    calls: list[tuple[str, str, str]] = []

    def fake_notify(event: str, subject: str, body: str) -> bool:
        calls.append((event, subject, body))
        return True

    with (
        patch.object(deployer, "_do_deploy", side_effect=RuntimeError("build blew up")),
        patch("hop3.plugins.email.notifications.notify", fake_notify),
        pytest.raises(RuntimeError, match="build blew up"),
    ):
        deployer.do_deploy(_App())

    assert calls, "expected a deploy-failure notification"
    event, subject, body = calls[0]
    assert event == "deploy-failure"
    assert "myapp" in subject
    assert "build blew up" in body


def test_notification_failure_does_not_mask_deploy_error():
    def boom(*_a, **_k):
        msg = "smtp down"
        raise RuntimeError(msg)

    # The ORIGINAL deploy error must propagate, not the notification error.
    with (
        patch.object(
            deployer, "_do_deploy", side_effect=ValueError("real deploy error")
        ),
        patch("hop3.plugins.email.notifications.notify", boom),
        pytest.raises(ValueError, match="real deploy error"),
    ):
        deployer.do_deploy(_App())


def test_success_does_not_notify():
    calls: list[object] = []

    with (
        patch.object(deployer, "_do_deploy", return_value=None),
        patch(
            "hop3.plugins.email.notifications.notify", lambda *a, **_k: calls.append(a)
        ),
    ):
        deployer.do_deploy(_App())

    assert not calls  # no alert on a successful deploy
