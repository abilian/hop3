# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Pure-core tests for the diagnostic bundle (no exec_run, no disk).

Covers the silent-502 classifier precedence and the listen-table / proxy_pass
parsers — the logic that decides signal vs noise.
"""

from __future__ import annotations

from typing import Any, cast

from hop3_testing.bundle import (
    SECTION_NAMES,
    Bundle,
    ProxyProbe,
    build_headline,
    classify,
    collect_diagnostic_bundle,
    parse_listen_ports,
    parse_proxy_pass_port,
)
from hop3_testing.targets.base import HttpResponse


def _bundle(classifier: str, run_id: str = "rid") -> Bundle:
    return Bundle(
        run_id=run_id,
        app="discourse",
        target_kind="ssh",
        classifier=classifier,  # type: ignore[arg-type]
        headline="(unused)",
    )


def test_bundle_why_points_at_build_section_for_build_failure():
    # A build failure's durable log lives in the `build` section; the pointer
    # must name it (the app is destroyed, so `hop3 app logs` is dead here).
    assert (
        _bundle("build-failure", run_id="rid-123").why
        == "hop3-test why rid-123 --section build"
    )


def test_bundle_why_falls_back_to_app_section():
    # Unknown/ok classifiers default to the `app` section, never crash.
    assert _bundle("ok").why == "hop3-test why rid --section app"


def _probe(**overrides) -> ProxyProbe:
    """A healthy-looking root probe; override fields per test."""
    defaults = {
        "effective_uid": "root",
        "deployer_kind": "uwsgi",
        "is_static": False,
        "vhost_found": True,
        "proxy_pass_port": 8000,
        "expected_port": 8000,
        "listen_table_available": True,
        "listen_ports": (8000,),
        "listen_owner": "uwsgi",
        "curl_status": 200,
        "container_state": "",
        "verdict": "ok",
    }
    defaults.update(overrides)
    return ProxyProbe(**defaults)


def test_headline_omits_fake_none_proxy_target_when_nothing_deployed():
    # A deploy that never came up: no proxy target, unknown deployer. The
    # headline must not render `127.0.0.1:None` (a fake URL) or a
    # `deployer kind: unknown` noise line.
    probe = _probe(
        proxy_pass_port=None,
        deployer_kind="unknown",
        effective_uid="unknown",
        listen_ports=(),
        listen_table_available=False,
        vhost_found=False,
        curl_status=0,
        verdict="app not deployed",
    )
    headline = build_headline(
        classifier="app-crash",
        app="startup",
        run_id="rid-x",
        probe=probe,
        sections={},
        http_front=None,
    )
    assert "127.0.0.1:None" not in headline
    assert "no vhost / app not deployed" in headline
    assert "deployer kind: unknown" not in headline


def test_classify_hint_startup_failure_wins():
    # A target that never came up is a startup failure, not an app crash.
    assert (
        classify({}, None, kind="unknown", http_front=None, hint="startup-failure")
        == "startup-failure"
    )


def test_startup_failure_headline_surfaces_deploy_error_and_points_at_deploy():
    # Verdict = the deploy error's key line; `why` points at the deploy section;
    # the meaningless app/proxy probe is not rendered.
    sections = {
        "deploy": "apt-get update ...\nE: Unable to fetch pkg X: Connection timed out\n"
    }
    headline = build_headline(
        classifier="startup-failure",
        app="deploy",
        run_id="rid-d",
        probe=_probe(proxy_pass_port=None, deployer_kind="unknown"),
        sections=sections,
        http_front=None,
    )
    assert "startup-failure — deploy" in headline
    assert "Connection timed out" in headline
    assert "127.0.0.1:None" not in headline
    assert headline.strip().endswith("why: hop3-test why rid-d --section deploy")


def test_collect_bundle_classifies_startup_failure_via_dead_target():
    # Through the real collection path: a target whose every probe fails is a
    # startup failure carrying the deploy log — not an app-crash.
    class _DeadTarget:
        def exec_run(self, cmd):
            return 1, "", "connection refused"

    bundle = collect_diagnostic_bundle(
        _DeadTarget(),
        app="deploy",
        classifier_hint="startup-failure",
        deploy_logs="E: hop3-deploy failed: server did not become ready",
        target_kind="ssh",
        persist=False,
    )
    assert bundle.classifier == "startup-failure"
    assert bundle.why == f"hop3-test why {bundle.run_id} --section deploy"
    assert "server did not become ready" in bundle.headline
    assert "127.0.0.1:None" not in bundle.headline


# --------------------------------------------------------------------------- #
# parse_proxy_pass_port
# --------------------------------------------------------------------------- #
def test_parse_proxy_pass_direct_form() -> None:
    conf = "server {\n  location / { proxy_pass http://127.0.0.1:55489; }\n}"
    assert parse_proxy_pass_port(conf) == 55489


def test_parse_proxy_pass_upstream_form() -> None:
    conf = (
        "upstream myapp { server 127.0.0.1:8123; }\n"
        "server { location / { uwsgi_pass myapp; } }"
    )
    assert parse_proxy_pass_port(conf) == 8123


def test_parse_proxy_pass_prefers_proxy_pass_over_upstream() -> None:
    conf = (
        "upstream myapp { server 127.0.0.1:1111; }\n"
        "location / { proxy_pass http://127.0.0.1:2222; }"
    )
    assert parse_proxy_pass_port(conf) == 2222


def test_parse_proxy_pass_none_for_static() -> None:
    assert parse_proxy_pass_port("server { root /var/www; }") is None


# --------------------------------------------------------------------------- #
# parse_listen_ports
# --------------------------------------------------------------------------- #
def test_parse_listen_ss() -> None:
    out = (
        "State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        'LISTEN 0      128    127.0.0.1:8000     0.0.0.0:*  users:(("uwsgi",pid=42,fd=3))\n'
    )
    ports, available, owners = parse_listen_ports(out)
    assert ports == (8000,)
    assert available is True
    assert owners[8000] == "uwsgi"


def test_parse_listen_netstat() -> None:
    out = (
        "Proto Recv-Q Send-Q Local Address  Foreign Address State  PID/Program\n"
        "tcp   0      0      127.0.0.1:9001 0.0.0.0:*       LISTEN 99/python\n"
    )
    ports, available, owners = parse_listen_ports(out)
    assert ports == (9001,)
    assert available is True
    assert owners[9001] == "python"


def test_parse_listen_proc_net_tcp_hex() -> None:
    # 0100007F:1F90 -> 127.0.0.1:8080, st 0A == LISTEN
    out = (
        "  sl  local_address rem_address   st\n"
        "   0: 0100007F:1F90 00000000:0000 0A 00000000\n"
        "   1: 0100007F:0050 00000000:0000 01 00000000\n"  # st 01 != LISTEN
    )
    ports, available, _ = parse_listen_ports(out)
    assert ports == (8080,)
    assert available is True


def test_parse_listen_unavailable() -> None:
    ports, available, _ = parse_listen_ports("(ss/netstat unavailable)")
    assert ports == ()
    assert available is False


def test_parse_listen_ss_wildcard_bind() -> None:
    # gunicorn's default `--bind 0.0.0.0:$PORT` shows as a 0.0.0.0 listen. A
    # `proxy_pass http://127.0.0.1:55767` reaches it, so it must be captured —
    # missing it produced the false proxy-502 for a healthy app.
    out = (
        "State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        'LISTEN 0      511    0.0.0.0:55767      0.0.0.0:*  users:(("gunicorn",pid=40432,fd=5))\n'
    )
    ports, available, owners = parse_listen_ports(out)
    assert ports == (55767,)
    assert available is True
    assert owners[55767] == "gunicorn"


def test_parse_listen_netstat_wildcard_and_ipv6() -> None:
    out = (
        "Proto Recv-Q Send-Q Local Address  Foreign Address State  PID/Program\n"
        "tcp   0      0      0.0.0.0:55767  0.0.0.0:*       LISTEN 40432/gunicorn\n"
        "tcp6  0      0      :::8080        :::*            LISTEN 55/python\n"
    )
    ports, _available, owners = parse_listen_ports(out)
    assert ports == (8080, 55767)
    assert owners[55767] == "gunicorn"


def test_parse_listen_peer_wildcard_port_not_matched() -> None:
    # The peer column `0.0.0.0:*` has `*` for a port, not digits — must not be
    # mistaken for a listen port.
    out = (
        "State  Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
        "LISTEN 0      511    0.0.0.0:55767      0.0.0.0:*\n"
    )
    ports, _, _ = parse_listen_ports(out)
    assert ports == (55767,)


def test_classify_wildcard_bound_app_is_not_proxy_502() -> None:
    # End-to-end shape from the report: the app is bound 0.0.0.0:55767 (gunicorn
    # default) and nginx proxies to :55767. Parse the real listen line, then
    # classify — with the wildcard bind now captured, it's healthy, NOT proxy-502.
    # (Revert the regex fix and parse yields (), _proxy_mismatch fires, this fails.)
    ss = (
        "State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
        "LISTEN 0 511 0.0.0.0:55767 0.0.0.0:*\n"
    )
    listen_ports, available, _ = parse_listen_ports(ss)
    probe = _probe(
        proxy_pass_port=55767,
        expected_port=55767,
        listen_table_available=available,
        listen_ports=listen_ports,
        curl_status=200,
    )
    assert classify({}, probe, kind="uwsgi", http_front=None, hint=None) != "proxy-502"


# --------------------------------------------------------------------------- #
# classify — precedence
# --------------------------------------------------------------------------- #
def test_classify_hint_wins() -> None:
    assert classify({}, None, kind="uwsgi", http_front=None, hint="build-failure") == (
        "build-failure"
    )


def test_classify_build_failure() -> None:
    sections = {"build": "error: gcc not found", "app": "", "deploy": ""}
    assert (
        classify(sections, _probe(), kind="uwsgi", http_front=None) == "build-failure"
    )


def test_classify_startup_failure_not_build_failure() -> None:
    # Regression: an app that BUILT OK but failed the start health-check must
    # be classified startup-failure, not build-failure. The deploy log carries
    # the deployer's abort ("failed to start" / "did not respond to health
    # checks" / "Deployer can't start app"), which the broad build-error regex
    # would otherwise match and point the user at the (green) build section.
    sections = {
        "build": "=== Nix Build Log ===\nStatus: SUCCESS\nBuild successful.",
        "app": "",
        "deploy": (
            "-> Build successful. Artifact: /nix/store/...\n"
            "> App 'sinatra-hello' failed to start within 60.0s.\n"
            "> Deployer can't start app: 'sinatra-hello' did not respond to "
            "health checks within 60.0s.\nERROR: deploying app failed\n"
        ),
    }
    assert (
        classify(sections, _probe(), kind="uwsgi", http_front=None) == "startup-failure"
    )


def test_classify_addon_unreachable() -> None:
    sections = {"app": "psycopg2.OperationalError: could not connect to server"}
    assert (
        classify(sections, _probe(), kind="uwsgi", http_front=None)
        == "addon-unreachable"
    )


def test_classify_static_ok_without_http() -> None:
    assert classify({}, _probe(is_static=True), kind="static", http_front=None) == "ok"


def test_classify_static_appcrash_on_5xx() -> None:
    http = HttpResponse(status=500, body="")
    assert (
        classify({}, _probe(is_static=True), kind="static", http_front=http)
        == "app-crash"
    )


def test_classify_docker_down_is_app_crash() -> None:
    probe = _probe(deployer_kind="docker", container_state="exited 1", curl_status=0)
    assert classify({}, probe, kind="docker", http_front=None) == "app-crash"


def test_classify_indeterminate_when_blind_and_nonroot() -> None:
    probe = _probe(
        effective_uid="hop3",
        listen_table_available=False,
        listen_ports=(),
        curl_status=0,
    )
    assert classify({}, probe, kind="uwsgi", http_front=None) == "indeterminate"


def test_classify_proxy_502_on_port_mismatch() -> None:
    # nginx -> :8000 but the app listens on :8123 (table readable, root)
    probe = _probe(proxy_pass_port=8000, listen_ports=(8123,), curl_status=0)
    assert classify({}, probe, kind="uwsgi", http_front=None) == "proxy-502"


def test_classify_not_proxy_502_when_backend_reachable() -> None:
    probe = _probe(proxy_pass_port=8000, listen_ports=(8000,), curl_status=200)
    assert classify({}, probe, kind="uwsgi", http_front=None) == "ok"


def test_classify_app_crash_on_traceback() -> None:
    sections = {"app": "Traceback (most recent call last):\nImportError: x"}
    probe = _probe(curl_status=200)  # listening, but app log shows a crash
    assert classify(sections, probe, kind="uwsgi", http_front=None) == "app-crash"


def test_classify_timeout() -> None:
    http = HttpResponse(status=0, body="")
    probe = _probe(curl_status=200, listen_ports=(8000,))
    assert classify({}, probe, kind="uwsgi", http_front=http) == "timeout"


# --------------------------------------------------------------------------- #
# build_headline
# --------------------------------------------------------------------------- #
def test_headline_is_bounded_and_has_why_pointer() -> None:
    probe = _probe(proxy_pass_port=8000, listen_ports=(), curl_status=0)
    headline = build_headline(
        classifier="proxy-502",
        app="flask-hello",
        run_id="2026-06-05T14-22-09Z-flask-hello-a1b2c3",
        probe=probe,
        sections={},
        http_front=HttpResponse(status=502, body=""),
    )
    lines = headline.splitlines()
    assert len(lines) <= 12
    assert lines[0].startswith("✗ proxy-502 — flask-hello")
    assert "run-id: 2026-06-05T14-22-09Z-flask-hello-a1b2c3" in headline
    assert (
        "why: hop3-test why 2026-06-05T14-22-09Z-flask-hello-a1b2c3 --section proxy"
        in headline
    )


class _FakeTarget:
    """A target whose exec_run replays canned output by command substring."""

    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def exec_run(self, cmd: str) -> tuple[int, str, str]:
        for key, val in self.responses.items():
            if key in cmd:
                return 0, val, ""
        return 0, "", ""


def test_collect_bundle_silent_502_end_to_end(tmp_path) -> None:
    """
    Full orchestration (collect -> probe -> classify -> headline -> write):
    nginx proxies to a port nothing listens on -> proxy-502, bundle persisted.
    """
    ss_table = (
        "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        'LISTEN 0 128 127.0.0.1:22 0.0.0.0:* users:(("sshd",pid=1,fd=3))\n'
    )
    target = _FakeTarget({
        "ss -ltnp": ss_table,
        "curl": "000",
        "uwsgi-enabled": "uwsgi",  # _detect_kind + app uwsgi ini
        "nginx/": "location / { proxy_pass http://127.0.0.1:55489; }",
        "id -un": "root",
    })

    bundle = collect_diagnostic_bundle(
        cast("Any", target),
        "flask-hello",
        target_kind="docker",
        base_dir=tmp_path,
    )

    assert bundle.classifier == "proxy-502"
    assert bundle.probe is not None
    assert bundle.probe.proxy_pass_port == 55489
    assert bundle.probe.listen_ports == (22,)
    # Persisted: dir basename == run_id, manifest + proxy_probe written.
    assert bundle.artifact_dir is not None
    assert bundle.artifact_dir.name == bundle.run_id
    assert (bundle.artifact_dir / "proxy_probe.txt").exists()
    assert (bundle.artifact_dir / "manifest.json").exists()
    assert "55489" in (bundle.artifact_dir / "proxy_probe.txt").read_text()


def test_collect_bundle_ok_is_not_persisted(tmp_path) -> None:
    """A healthy backend (curl 200, port matches) classifies ok and writes nothing."""
    ss_table = (
        "State Recv-Q Send-Q Local Address:Port\n"
        "LISTEN 0 128 127.0.0.1:55489 0.0.0.0:*\n"
    )
    target = _FakeTarget({
        "ss -ltnp": ss_table,
        "curl": "200",
        "uwsgi-enabled": "uwsgi",
        "nginx/": "location / { proxy_pass http://127.0.0.1:55489; }",
        "id -un": "root",
    })
    bundle = collect_diagnostic_bundle(
        cast("Any", target),
        "flask-hello",
        target_kind="docker",
        base_dir=tmp_path,
    )
    assert bundle.classifier == "ok"
    assert bundle.artifact_dir is None  # ok bundles are never persisted by default
    assert list(tmp_path.iterdir()) == []


def test_collect_bundle_ok_is_persisted_when_forced(tmp_path) -> None:
    """
    force_persist writes even an ok-classified bundle: a check.py / HTTP-
    `contains` failure serves fine (classifier ok) yet must leave a bundle that
    `hop3-test why` can replay. Regression for check.py failures showing
    'No bundle found'.
    """
    ss_table = (
        "State Recv-Q Send-Q Local Address:Port\n"
        "LISTEN 0 128 127.0.0.1:55489 0.0.0.0:*\n"
    )
    target = _FakeTarget({
        "ss -ltnp": ss_table,
        "curl": "200",
        "uwsgi-enabled": "uwsgi",
        "nginx/": "location / { proxy_pass http://127.0.0.1:55489; }",
        "id -un": "root",
    })
    bundle = collect_diagnostic_bundle(
        cast("Any", target),
        "flask-hello",
        target_kind="docker",
        base_dir=tmp_path,
        force_persist=True,
    )
    assert bundle.classifier == "ok"
    assert bundle.artifact_dir is not None  # forced -> written despite ok
    assert bundle.artifact_dir.name == bundle.run_id
    assert (bundle.artifact_dir / "manifest.json").exists()


def test_headline_indeterminate_icon() -> None:
    probe = _probe(effective_uid="hop3", listen_table_available=False, listen_ports=())
    headline = build_headline(
        classifier="indeterminate",
        app="x",
        run_id="rid",
        probe=probe,
        sections={},
        http_front=None,
    )
    assert headline.startswith("? indeterminate — x")


def test_bundle_captures_resources_section(tmp_path) -> None:
    """
    The bundle records host disk/mem in a `resources` section, so disk
    pressure — behind spring-boot's truncated jar and forgejo's GC'd closure —
    is self-evident instead of a black box. (`df -h` is first in the fake's
    response map so it wins for the resources command.)
    """
    target = _FakeTarget({
        "df -h": "Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 40G 40G 0 100% /",
        "id -un": "root",
        "ss -ltnp": "LISTEN 0 128 127.0.0.1:22",
        "nginx/": "proxy_pass http://127.0.0.1:8000;",
        "curl": "000",
    })
    bundle = collect_diagnostic_bundle(
        cast("Any", target), "someapp", target_kind="ssh", base_dir=tmp_path
    )
    assert "resources" in SECTION_NAMES
    assert "100%" in bundle.sections["resources"]
