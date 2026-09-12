# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for nginx ops.

The exec seam is faked via ``OpContext.exec`` (a ``FakeExec``); no real
nginx/systemctl runs. Tests pin resolved paths with ``set_path`` and route
``run`` calls, then assert on the result + recorded argvs.
"""

from __future__ import annotations

import math

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
    monkeypatch.setattr(
        nginx_ops,
        "_verify_reload",
        lambda _since, _offset: (
            None if applied else (reason or "no fresh worker processes appeared")
        ),
    )


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
    monkeypatch.setattr(nginx_ops, "_verify_reload", lambda _s, _o: None)
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
    monkeypatch.setattr(nginx_ops, "_verify_reload", lambda _s, _o: None)
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


def test_verify_reload_true_when_worker_forked_after_threshold(tmp_path, monkeypatch):
    proc = _make_proc(tmp_path, [(11, 100), (12, 300)])
    monkeypatch.setattr(nginx_ops, "_PROC_ROOT", proc)
    monkeypatch.setattr(nginx_ops, "_sleep", lambda _s: None)
    assert nginx_ops._verify_reload(250.0, 0) is None


def test_verify_reload_false_when_all_workers_predate_threshold(tmp_path, monkeypatch):
    proc = _make_proc(tmp_path, [(11, 100), (12, 200)])
    monkeypatch.setattr(nginx_ops, "_PROC_ROOT", proc)
    monkeypatch.setattr(nginx_ops, "_sleep", lambda _s: None)
    assert nginx_ops._verify_reload(250.0, 0) is not None


def test_verify_reload_false_when_threshold_unknown(monkeypatch):
    # No /proc uptime (since_ticks=None) -> inconclusive -> False (caller fails loud),
    # never a false "applied".
    monkeypatch.setattr(nginx_ops, "_sleep", lambda _s: None)
    assert nginx_ops._verify_reload(None, 0) is not None


# --- _verify_reload: two phases, gated on the error log ------------------
#
# A reload nginx accepted without logging an error always forks workers; on a
# loaded host that can take more than the 2 s an idle one needs (an e2e deploy
# failed on exactly that while a build ran alongside). A rejected reload logs
# [emerg] at once and must not wait the long budget.


def _count_sleeps(monkeypatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr(nginx_ops, "_sleep", sleeps.append)
    return sleeps


def test_verify_reload_fails_fast_when_nginx_logged_a_rejection(monkeypatch):
    monkeypatch.setattr(nginx_ops, "_nginx_worker_starttimes", lambda: [100.0])
    monkeypatch.setattr(
        nginx_ops, "_last_reload_error", lambda _o: "[emerg] bind() failed"
    )
    sleeps = _count_sleeps(monkeypatch)
    assert nginx_ops._verify_reload(250.0, 0) == "[emerg] bind() failed"
    assert len(sleeps) == nginx_ops._RELOAD_VERIFY_ATTEMPTS


def test_verify_reload_keeps_waiting_when_nginx_logged_nothing(monkeypatch):
    polls = 0

    def slow_fork() -> list[float]:
        nonlocal polls
        polls += 1
        return [300.0] if polls > nginx_ops._RELOAD_VERIFY_ATTEMPTS + 30 else [100.0]

    monkeypatch.setattr(nginx_ops, "_nginx_worker_starttimes", slow_fork)
    monkeypatch.setattr(nginx_ops, "_last_reload_error", lambda _o: None)
    sleeps = _count_sleeps(monkeypatch)
    assert nginx_ops._verify_reload(250.0, 0) is None
    assert len(sleeps) > nginx_ops._RELOAD_VERIFY_ATTEMPTS


def test_verify_reload_gives_up_after_the_slow_budget(monkeypatch):
    monkeypatch.setattr(nginx_ops, "_nginx_worker_starttimes", lambda: [100.0])
    monkeypatch.setattr(nginx_ops, "_last_reload_error", lambda _o: None)
    sleeps = _count_sleeps(monkeypatch)
    assert nginx_ops._verify_reload(250.0, 0) is not None
    assert len(sleeps) == (
        nginx_ops._RELOAD_VERIFY_ATTEMPTS + nginx_ops._RELOAD_VERIFY_SLOW_ATTEMPTS
    )


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


class TestTheGiveUpMessageCarriesItsEvidence:
    """
    "No fresh worker appeared" is a conclusion, not an observation. On its own
    it cannot be acted on: nginx forking nothing, this check missing a worker
    it did fork, and nginx logging its errors somewhere unreadable all produce
    the same sentence. The third is the normal case in a container running
    nginx with `daemon off`, where the error log is stderr and
    /var/log/nginx/error.log stays empty — so the discriminator between
    "rejected" and "slow" is silently unavailable and every failure looks slow.
    """

    def test_it_reports_the_reference_tick(self, monkeypatch) -> None:
        monkeypatch.setattr(nginx_ops, "_nginx_worker_starttimes", list)
        monkeypatch.setattr(nginx_ops, "_error_log_size", lambda: 0)
        assert "reload reference 4242 ticks" in nginx_ops._no_fresh_worker(4242.0, 0)

    def test_it_reports_the_worker_start_times_it_saw(self, monkeypatch) -> None:
        """The number next to the reference is what makes the verdict checkable."""
        monkeypatch.setattr(
            nginx_ops, "_nginx_worker_starttimes", lambda: [100.0, 90.0]
        )
        monkeypatch.setattr(nginx_ops, "_error_log_size", lambda: 0)
        message = nginx_ops._no_fresh_worker(4242.0, 0)
        assert "worker start times seen: 90, 100" in message

    def test_it_says_when_it_saw_no_workers_at_all(self, monkeypatch) -> None:
        monkeypatch.setattr(nginx_ops, "_nginx_worker_starttimes", list)
        monkeypatch.setattr(nginx_ops, "_error_log_size", lambda: 0)
        assert "worker start times seen: none" in nginx_ops._no_fresh_worker(1.0, 0)

    def test_an_unreadable_error_log_is_named_as_such(self, monkeypatch) -> None:
        """Otherwise an empty log reads as 'nginx reported nothing wrong'."""
        monkeypatch.setattr(nginx_ops, "_nginx_worker_starttimes", list)
        monkeypatch.setattr(nginx_ops, "_error_log_size", lambda: 0)
        message = nginx_ops._no_fresh_worker(1.0, 0)
        assert "unreadable/absent" in message
        assert "daemon off" in message, "name the container case explicitly"

    def test_a_readable_log_reports_how_much_it_grew(self, monkeypatch) -> None:
        monkeypatch.setattr(nginx_ops, "_nginx_worker_starttimes", list)
        monkeypatch.setattr(nginx_ops, "_error_log_size", lambda: 500)
        assert "200 new bytes" in nginx_ops._no_fresh_worker(1.0, 300)

    def test_a_missing_uptime_says_the_reference_was_unavailable(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(nginx_ops, "_nginx_worker_starttimes", list)
        monkeypatch.setattr(nginx_ops, "_error_log_size", lambda: 0)
        assert "reference unavailable" in nginx_ops._no_fresh_worker(None, 0)


class TestTheReferenceTickIsComparableToStarttime:
    """
    `/proc/uptime` is seconds with two decimals; `starttime` is an integer
    tick count. Multiplying the parsed float by CLK_TCK does not land on the
    integer — `81408.99 * 100` is `8140899.000000001` — so a worker forking
    in that same centisecond, reporting exactly `8140899`, failed the `>=`
    test. Nothing else qualified, the 15s budget lapsed, and a reload that
    had applied was reported as "nginx kept the previous config".

    Seen in the e2e suite: `reload reference 8140899 ticks; worker start
    times seen: 8140899, 8140899` — a failure whose own evidence showed the
    workers were fresh.
    """

    @staticmethod
    def reference(uptime: str, monkeypatch, tmp_path) -> float:
        (tmp_path / "uptime").write_text(f"{uptime} 100000.00\n")
        monkeypatch.setattr(nginx_ops, "_PROC_ROOT", tmp_path)
        return nginx_ops._ticks_since_boot()

    def test_an_uptime_that_multiplies_high_does_not_reject_a_fresh_worker(
        self, monkeypatch, tmp_path
    ) -> None:
        assert float("81408.99") * 100 > 8140899, "premise: the float rounds up"
        reference = self.reference("81408.99", monkeypatch, tmp_path)
        assert reference <= 8140899, "a worker forked in this centisecond is fresh"

    @pytest.mark.parametrize(
        "uptime", ["81408.99", "74444.56", "12345.67", "0.01", "999999.99"]
    )
    def test_a_worker_forked_in_the_sampled_centisecond_always_counts(
        self, uptime, monkeypatch, tmp_path
    ) -> None:
        reference = self.reference(uptime, monkeypatch, tmp_path)
        same_tick = math.floor(float(uptime) * 100)
        assert same_tick >= reference

    def test_it_is_a_whole_number_of_ticks(self, monkeypatch, tmp_path) -> None:
        reference = self.reference("81408.99", monkeypatch, tmp_path)
        assert reference == int(reference)

    def test_it_never_runs_ahead_of_the_sample(self, monkeypatch, tmp_path) -> None:
        """Flooring may be one tick early; it must never be late."""
        reference = self.reference("81408.99", monkeypatch, tmp_path)
        assert reference <= float("81408.99") * 100

    def test_an_unreadable_uptime_is_still_none(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(nginx_ops, "_PROC_ROOT", tmp_path / "nope")
        assert nginx_ops._ticks_since_boot() is None
