# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for nginx ops.

The exec seam is faked via ``OpContext.exec`` (a ``FakeExec``); no real
nginx/systemctl runs. Tests pin resolved paths with ``set_path`` and route
``run`` calls, then assert on the result + recorded argvs.
"""

from __future__ import annotations

import pytest
from hop3_rootd import PROTOCOL_VERSION
from hop3_rootd.exec import CommandResult, CommandTimeoutError, InvalidBinaryError
from hop3_rootd.ops import get_handler, nginx as nginx_ops
from hop3_rootd.ops._base import OpContext
from hop3_rootd.ops.nginx import (
    NginxBinaryNotFoundError,
    NginxReloadNotAppliedError,
)
from hop3_rootd.protocol import Request
from hop3_rootd.state import State

from tests.a_unit._fakes import FakeExec, fail, ok


def _ctx() -> tuple[OpContext, FakeExec]:
    fake = FakeExec()
    return OpContext(
        state=State(),
        save_state=lambda: None,
        now_iso=lambda: "2026-04-24T15:30:00+00:00",
        new_rule_id=lambda: "rule-test",
        exec=fake,
    ), fake


def _req(op: str) -> Request:
    return Request(v=PROTOCOL_VERSION, id="r1", op=op, args={})


def _simulate_reload(monkeypatch, *, applied: bool, reason: str | None = None) -> None:
    """
    Stub the post-reload verification at its decision seams.

    applied=True: nginx spawned a fresh worker (reload took effect).
    applied=False: no fresh worker (nginx rejected the new config).
    The real /proc / error-log parsing behind these seams is covered by the
    dedicated helper tests below.
    """
    monkeypatch.setattr(nginx_ops, "_reload_applied", lambda _since: applied)
    monkeypatch.setattr(nginx_ops, "_last_reload_error", lambda _offset: reason)


# --- nginx.reload --------------------------------------------------------


def test_reload_uses_systemctl_when_available(monkeypatch):
    handler = get_handler("nginx.reload")
    assert handler is not None
    _simulate_reload(monkeypatch, applied=True)
    ctx, fake = _ctx()
    fake.set_path("systemctl", "/usr/bin/systemctl")
    fake.set_path("nginx", None)  # nginx not installed

    result = handler(_req("nginx.reload"), ctx)

    assert result == {"method": "systemctl"}
    reload_calls = [c for c in fake.calls if "reload" in c]
    assert reload_calls[0][0] == "/usr/bin/systemctl"
    assert "nginx" in reload_calls[0]


def test_reload_falls_back_to_nginx_s_reload(monkeypatch):
    """systemctl missing or fails → try `nginx -s reload`."""
    handler = get_handler("nginx.reload")
    assert handler is not None
    _simulate_reload(monkeypatch, applied=True)
    ctx, fake = _ctx()
    fake.set_path("systemctl", "/usr/bin/systemctl")
    fake.set_path("nginx", "/usr/sbin/nginx")
    # systemctl reload fails; `nginx -s reload` succeeds (default ok()).
    fake.on(
        lambda argv: any("systemctl" in tok for tok in argv),
        fail("systemd not running"),
    )

    result = handler(_req("nginx.reload"), ctx)

    assert result == {"method": "nginx -s reload"}
    # Both methods were attempted.
    assert fake.calls_with("/usr/bin/systemctl")
    assert fake.calls_with("-s")  # the `nginx -s reload` fallback


def test_reload_fails_loud_when_config_not_applied(monkeypatch):
    """
    rc=0 but nginx kept the old config (no worker cycle) → raise, with the
    nginx error-log reason surfaced so the deploy aborts actionably.
    """
    handler = get_handler("nginx.reload")
    assert handler is not None
    _simulate_reload(
        monkeypatch,
        applied=False,
        reason="2026/07/16 18:28:15 [emerg] bind() to 127.0.0.1:8443 failed "
        "(98: Address already in use)",
    )
    ctx, fake = _ctx()
    fake.set_path("systemctl", "/usr/bin/systemctl")
    fake.set_path("nginx", "/usr/sbin/nginx")  # rc=0 (default ok())

    with pytest.raises(NginxReloadNotAppliedError, match="did not apply"):
        handler(_req("nginx.reload"), ctx)


def test_reload_not_applied_has_fallback_reason(monkeypatch):
    """When the error log is unreadable, still fail loud with a usable hint."""
    handler = get_handler("nginx.reload")
    assert handler is not None
    _simulate_reload(monkeypatch, applied=False, reason=None)
    ctx, fake = _ctx()
    fake.set_path("systemctl", "/usr/bin/systemctl")
    fake.set_path("nginx", "/usr/sbin/nginx")

    with pytest.raises(NginxReloadNotAppliedError, match="no fresh worker processes"):
        handler(_req("nginx.reload"), ctx)


def test_reload_raises_when_no_method_available():
    """No systemctl, no nginx → raise."""
    handler = get_handler("nginx.reload")
    assert handler is not None
    ctx, fake = _ctx()
    fake.set_path("systemctl", None)
    fake.set_path("nginx", None)
    with pytest.raises(NginxBinaryNotFoundError, match="no nginx-reload method"):
        handler(_req("nginx.reload"), ctx)


def test_reload_raises_when_all_methods_fail():
    handler = get_handler("nginx.reload")
    assert handler is not None
    ctx, fake = _ctx()
    fake.set_path("systemctl", "/usr/bin/systemctl")
    fake.set_path("nginx", "/usr/sbin/nginx")
    fake.on(lambda argv: True, fail("error"))
    with pytest.raises(
        NginxBinaryNotFoundError, match="all nginx-reload methods failed"
    ):
        handler(_req("nginx.reload"), ctx)


# --- nginx.validate_config -----------------------------------------------


def test_validate_returns_valid_true_on_success():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    ctx, fake = _ctx()
    fake.set_path("nginx", "/usr/sbin/nginx")
    # rc 0 → valid. (nginx -t writes diagnostics to stderr even on success,
    # but the success path doesn't read it.)
    fake.on(lambda argv: True, ok())
    result = handler(_req("nginx.validate_config"), ctx)
    assert result == {"valid": True}


def test_validate_returns_valid_false_with_errors():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    ctx, fake = _ctx()
    fake.set_path("nginx", "/usr/sbin/nginx")
    stderr = (
        "nginx: [emerg] unexpected '}' in /etc/nginx/sites-enabled/default:42\n"
        "nginx: configuration file /etc/nginx/nginx.conf test failed\n"
    )
    fake.on(lambda argv: True, fail(stderr=stderr))

    result = handler(_req("nginx.validate_config"), ctx)

    assert result["valid"] is False
    assert any("[emerg]" in line for line in result["errors"])
    assert any("test failed" in line for line in result["errors"])
    assert "raw_stderr" in result


def test_validate_filters_warnings_in_errors_list():
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    ctx, fake = _ctx()
    fake.set_path("nginx", "/usr/sbin/nginx")
    stderr = "Some chatter\nnginx: [warn] something weird\nnginx: [emerg] real error\n"
    fake.on(lambda argv: True, fail(stderr=stderr))

    result = handler(_req("nginx.validate_config"), ctx)
    # Both [warn] and [emerg] lines surface in errors; "Some chatter" is dropped.
    assert any("[warn]" in line for line in result["errors"])
    assert any("[emerg]" in line for line in result["errors"])
    assert not any("chatter" in line for line in result["errors"])


def test_validate_raises_when_nginx_missing():
    """nginx resolves to None (not on PATH / not allow-listed) → raise."""
    handler = get_handler("nginx.validate_config")
    assert handler is not None
    ctx, fake = _ctx()
    fake.set_path("nginx", None)
    with pytest.raises(NginxBinaryNotFoundError, match="not on allow-list"):
        handler(_req("nginx.validate_config"), ctx)
    # Allow-list rejection itself is covered at the exec seam
    # (test_find_nft_binary_raises_when_not_in_allowlist); the op only owns
    # the None → raise contract.
    assert fake.calls == []


# --- reload fallback across methods --------------------------------------


class _RaisingExec:
    """
    Minimal Exec double: raises a chosen exception for argvs matching a
    substring, otherwise returns rc=0. FakeExec's run() can't raise, so this
    covers the InvalidBinaryError / CommandTimeoutError continue-branches.
    """

    def __init__(self, raise_on: str, exc: Exception, paths: dict[str, str]) -> None:
        self._raise_on = raise_on
        self._exc = exc
        self._paths = paths

    def resolve(self, name: str) -> str | None:
        return self._paths.get(name)

    def run(self, argv, **_kw) -> CommandResult:
        if any(self._raise_on in tok for tok in argv):
            raise self._exc
        return CommandResult(argv=list(argv), returncode=0, stdout="", stderr="")


def _ctx_with(exec_obj) -> OpContext:
    return OpContext(
        state=State(),
        save_state=lambda: None,
        now_iso=lambda: "t",
        new_rule_id=lambda: "r",
        exec=exec_obj,
    )


def test_reload_timeout_falls_through_to_next_method(monkeypatch):
    """
    A wedged systemctl (CommandTimeoutError) must not strand the deploy —
    the `nginx -s reload` fallback still runs.
    """
    monkeypatch.setattr(nginx_ops, "_reload_applied", lambda _s: True)
    exc = CommandTimeoutError(["/usr/bin/systemctl", "reload", "nginx"], 10.0)
    ctx = _ctx_with(
        _RaisingExec(
            "systemctl",
            exc,
            {"systemctl": "/usr/bin/systemctl", "nginx": "/usr/sbin/nginx"},
        )
    )
    handler = get_handler("nginx.reload")
    assert handler is not None
    assert handler(_req("nginx.reload"), ctx) == {"method": "nginx -s reload"}


def test_reload_invalid_binary_falls_through_to_next_method(monkeypatch):
    monkeypatch.setattr(nginx_ops, "_reload_applied", lambda _s: True)
    exc = InvalidBinaryError("/usr/bin/systemctl")
    ctx = _ctx_with(
        _RaisingExec(
            "systemctl",
            exc,
            {"systemctl": "/usr/bin/systemctl", "nginx": "/usr/sbin/nginx"},
        )
    )
    handler = get_handler("nginx.reload")
    assert handler is not None
    assert handler(_req("nginx.reload"), ctx) == {"method": "nginx -s reload"}


# --- _nginx_worker_starttimes: real /proc parsing (fake tree) ------------


def _stat(pid: int, comm: str, starttime: int) -> str:
    """A /proc/PID/stat line with `starttime` at field 22 (index 19 post-comm)."""
    after_comm = ["S", *["0"] * 18, str(starttime)]  # state + 18 fillers + starttime
    return f"{pid} ({comm}) " + " ".join(after_comm)


def _make_proc(tmp_path, workers, *, master_start=None) -> object:
    proc = tmp_path / "proc"
    for pid, st in workers:
        d = proc / str(pid)
        d.mkdir(parents=True)
        (d / "cmdline").write_bytes(b"nginx: worker process\x00")
        (d / "stat").write_text(_stat(pid, "nginx", st))
    if master_start is not None:
        d = proc / "999"
        d.mkdir(parents=True)
        (d / "cmdline").write_bytes(b"nginx: master process /usr/sbin/nginx\x00")
        (d / "stat").write_text(_stat(999, "nginx", master_start))
    # a non-nginx process and a non-numeric dir, both must be ignored
    other = proc / "1000"
    other.mkdir(parents=True)
    (other / "cmdline").write_bytes(b"/usr/bin/python3\x00app.py\x00")
    (other / "stat").write_text(_stat(1000, "python3", 500))
    (proc / "self").mkdir()
    return proc


def test_worker_starttimes_returns_only_workers(tmp_path, monkeypatch):
    proc = _make_proc(tmp_path, [(11, 100), (12, 200)], master_start=50)
    monkeypatch.setattr(nginx_ops, "_PROC_ROOT", proc)
    assert sorted(nginx_ops._nginx_worker_starttimes()) == [100.0, 200.0]


def test_reload_applied_true_when_worker_forked_after_threshold(tmp_path, monkeypatch):
    proc = _make_proc(tmp_path, [(11, 100), (12, 300)])
    monkeypatch.setattr(nginx_ops, "_PROC_ROOT", proc)
    monkeypatch.setattr(nginx_ops, "_sleep", lambda _s: None)
    assert nginx_ops._reload_applied(250.0) is True


def test_reload_applied_false_when_all_workers_predate_threshold(tmp_path, monkeypatch):
    proc = _make_proc(tmp_path, [(11, 100), (12, 200)])
    monkeypatch.setattr(nginx_ops, "_PROC_ROOT", proc)
    monkeypatch.setattr(nginx_ops, "_sleep", lambda _s: None)
    assert nginx_ops._reload_applied(250.0) is False


def test_reload_applied_false_when_threshold_unknown(monkeypatch):
    # No /proc uptime (since_ticks=None) -> inconclusive -> False (caller fails loud),
    # never a false "applied".
    monkeypatch.setattr(nginx_ops, "_sleep", lambda _s: None)
    assert nginx_ops._reload_applied(None) is False


# --- _last_reload_error: scoped to bytes written during this reload ------


def test_last_reload_error_scopes_to_new_bytes(tmp_path, monkeypatch):
    log = tmp_path / "error.log"
    log.write_text("2026/07/16 10:00:00 [emerg] stale unrelated cert error\n")
    offset = log.stat().st_size
    with log.open("a") as fh:
        fh.write("2026/07/16 18:28:15 [emerg] bind() to 127.0.0.1:8443 failed\n")
    monkeypatch.setattr(nginx_ops, "_NGINX_ERROR_LOG", log)

    reason = nginx_ops._last_reload_error(offset)
    assert reason is not None
    assert "bind() to 127.0.0.1:8443" in reason
    assert "stale unrelated" not in reason  # older line excluded by the offset


def test_last_reload_error_none_when_no_new_emerg(tmp_path, monkeypatch):
    log = tmp_path / "error.log"
    log.write_text("2026/07/16 10:00:00 [emerg] old\n")
    offset = log.stat().st_size
    with log.open("a") as fh:
        fh.write("2026/07/16 18:28:15 [notice] harmless notice\n")
    monkeypatch.setattr(nginx_ops, "_NGINX_ERROR_LOG", log)
    assert nginx_ops._last_reload_error(offset) is None


def test_last_reload_error_none_when_log_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(nginx_ops, "_NGINX_ERROR_LOG", tmp_path / "absent.log")
    assert nginx_ops._last_reload_error(0) is None
