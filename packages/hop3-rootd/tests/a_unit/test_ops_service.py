# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for ``service.reload``.

This op replaced three deployer call sites that ran ``sudo -n systemctl
reload <svc>`` directly — the pattern the privilege model rules out, and one
that fails outright where the ``hop3`` user has no passwordless sudo. The
PostgreSQL site also discarded the result, so a rewritten ``pg_hba.conf`` that
never applied looked identical to one that did.
"""

from __future__ import annotations

import pytest
from hop3_rootd import PROTOCOL_VERSION
from hop3_rootd.exec import CommandTimeoutError
from hop3_rootd.ops import get_handler
from hop3_rootd.ops._base import OpContext
from hop3_rootd.ops.service import (
    RELOADABLE_SERVICES,
    ServiceNotAllowedError,
    ServiceReloadFailedError,
)
from hop3_rootd.protocol import Request
from hop3_rootd.state import State

from tests.a_unit._fakes import FakeExec, fail


def _ctx() -> tuple[OpContext, FakeExec]:
    """Context whose exec resolves nothing until a test pins a path.

    FakeExec.resolve invents /usr/sbin/<name> for any binary, which would make
    "no reload method available on this host" untestable.
    """
    fake = FakeExec()
    fake.set_path("supervisorctl", None)
    fake.set_path("systemctl", None)
    return OpContext(
        state=State(),
        save_state=lambda: None,
        now_iso=lambda: "2026-09-02T10:00:00+00:00",
        new_rule_id=lambda: "rule-test",
        exec=fake,
    ), fake


def _req(service: object) -> Request:
    return Request(
        v=PROTOCOL_VERSION, id="r1", op="service.reload", args={"service": service}
    )


def test_supervisorctl_is_tried_first():
    ctx, fake = _ctx()
    fake.set_path("supervisorctl", "/usr/bin/supervisorctl")
    fake.set_path("systemctl", "/usr/bin/systemctl")

    result = get_handler("service.reload")(_req("caddy"), ctx)

    assert result == {"service": "caddy", "method": "supervisorctl"}
    assert fake.calls[0][0] == "/usr/bin/supervisorctl"
    assert fake.calls[0][1:] == ["restart", "caddy"]


def test_falls_back_to_systemctl_when_supervisorctl_fails():
    ctx, fake = _ctx()
    fake.set_path("supervisorctl", "/usr/bin/supervisorctl")
    fake.set_path("systemctl", "/usr/bin/systemctl")
    fake.on(lambda argv: "supervisorctl" in argv[0], fail("no such process"))

    result = get_handler("service.reload")(_req("postgresql"), ctx)

    assert result["method"] == "systemctl reload"
    assert fake.calls[-1][1:] == ["reload", "postgresql"]


def test_systemd_only_host_works():
    ctx, fake = _ctx()
    fake.set_path("supervisorctl", None)
    fake.set_path("systemctl", "/usr/bin/systemctl")

    result = get_handler("service.reload")(_req("traefik"), ctx)

    assert result["method"] == "systemctl reload"


def test_reload_or_restart_is_tried_when_reload_is_unsupported():
    # Not every unit implements `reload`; systemd offers reload-or-restart.
    ctx, fake = _ctx()
    fake.set_path("supervisorctl", None)
    fake.set_path("systemctl", "/usr/bin/systemctl")
    # `in argv` is exact element membership, so this matches "reload" and not
    # "reload-or-restart".
    fake.on(lambda argv: "reload" in argv, fail("Unit does not support reload"))

    result = get_handler("service.reload")(_req("postgresql"), ctx)

    assert result["method"] == "systemctl reload-or-restart"
    assert [c[1] for c in fake.calls] == ["reload", "reload-or-restart"]


def test_a_service_not_on_the_allow_list_is_refused():
    # The service name reaches argv, so this must not be a free parameter.
    ctx, fake = _ctx()
    with pytest.raises(ServiceNotAllowedError, match="not reloadable"):
        get_handler("service.reload")(_req("sshd"), ctx)
    assert fake.calls == [], "a refused service must not run anything"


@pytest.mark.parametrize("bad", [None, 42, "", ["caddy"]])
def test_a_non_string_service_is_refused(bad):
    ctx, _ = _ctx()
    with pytest.raises(ServiceNotAllowedError):
        get_handler("service.reload")(_req(bad), ctx)


def test_every_allowed_service_is_a_plain_name():
    # A name carrying a flag or separator would change the argv's meaning.
    for name in RELOADABLE_SERVICES:
        assert name.replace("-", "").isalnum(), name
        assert not name.startswith("-"), name


def test_no_method_available_fails_loudly():
    ctx, _ = _ctx()
    with pytest.raises(ServiceReloadFailedError, match="no reload method available"):
        get_handler("service.reload")(_req("redis"), ctx)


def test_all_methods_failing_reports_the_last_error():
    ctx, fake = _ctx()
    fake.set_path("supervisorctl", None)
    fake.set_path("systemctl", "/usr/bin/systemctl")
    fake.on(lambda argv: True, fail("Unit not found", returncode=5))

    with pytest.raises(ServiceReloadFailedError, match="Unit not found"):
        get_handler("service.reload")(_req("mysql"), ctx)


def test_a_timeout_is_not_swallowed_into_success():
    ctx, fake = _ctx()
    fake.set_path("supervisorctl", None)
    fake.set_path("systemctl", "/usr/bin/systemctl")

    def _timeout(argv, **_kwargs):
        raise CommandTimeoutError(argv, 15.0)

    fake.run = _timeout  # type: ignore[method-assign]

    with pytest.raises(ServiceReloadFailedError):
        get_handler("service.reload")(_req("caddy"), ctx)
