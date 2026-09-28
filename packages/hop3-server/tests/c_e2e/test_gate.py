# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: the access gate, through each reverse proxy (ADR 062 §Acceptance).

A login-less app is deployed with `[access] require = "auth"` on nginx, Caddy
and Traefik, and signed into the way a browser does it: curl inside the
container, with a cookie jar, resolving the app's and the admin domain's names
to the proxy. The app echoes what reaches it, so each check reads the app's own
answer: who it was told is asking, and which cookies it received.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tarfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from hop3_testing.targets.constants import hermetic_cli_cwd

from .conftest import (
    _start_hop3_container,
    _stop_hop3_container,
    cli_env,
    deploy_app_dir,
    deploy_flask_app,
    init_git_repo,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    import docker

ADMIN = "admin.test.local"
#: The harness fixture that carries the gate into runs on real servers.
GATED_FIXTURE = Path(__file__).parents[4] / "apps/test-apps-procfile/180-flask-gated"
GATED_FIXTURE_HOST = "flask-gated.test.local"
NOTES = "notes.test.local"  # role member, /hook public
WIKI = "wiki.test.local"  # role viewer
PASSWORD = "gate-e2e-password"

# Everything the app is told, and a marker saying which app answered.
WHOAMI = """
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def whoami(path):
    return jsonify(
        app="{name}",
        path="/" + path,
        user=request.headers.get("X-Hop3-User", ""),
        role=request.headers.get("X-Hop3-Role", ""),
        cookie=request.headers.get("Cookie", ""),
    )
"""


class Browser:
    """curl in the container with its own cookie jar; no redirect is followed."""

    def __init__(self, info: dict[str, Any], name: str) -> None:
        self.container = info["container"]
        self.jar = f"/tmp/jar-{name}-{time.monotonic_ns()}"

    def request(
        self,
        url: str,
        *,
        form: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        jar: bool = True,
    ) -> tuple[int, dict[str, str], str]:
        cmd = ["curl", "-sk", "-D", "-", "--max-time", "20"]
        for host in (ADMIN, NOTES, WIKI):
            cmd += ["--resolve", f"{host}:443:127.0.0.1"]
        if jar:
            cmd += ["-b", self.jar, "-c", self.jar]
        for key, value in (headers or {}).items():
            cmd += ["-H", f"{key}: {value}"]
        if form is not None:  # a form is a POST, even an empty one
            cmd += ["--data", ""]
            for key, value in form.items():
                cmd += ["--data-urlencode", f"{key}={value}"]
        output = self.container.exec_run([*cmd, url]).output.decode(errors="replace")
        head, _, body = output.partition("\r\n\r\n")
        lines = head.split("\r\n")
        status = int(lines[0].split()[1]) if lines[0].startswith("HTTP") else 0
        fields = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
        return status, {k.lower(): v for k, v in fields.items()}, body

    def sign_in(self, username: str) -> Browser:
        """Sign in on the admin domain, as a user does once."""
        status, headers, _ = self.request(
            f"https://{ADMIN}/auth/login",
            form={"username": username, "password": PASSWORD},
        )
        assert status in {302, 303}, (status, headers)
        assert not headers["location"].startswith("/auth/login"), headers["location"]
        return self

    def continue_to(self, next_url: str) -> tuple[int, dict[str, str], str]:
        """The login page with a ``next``, as a signed-in browser opens it."""
        return self.request(
            f"https://{ADMIN}/auth/login?next={quote(next_url, safe='')}"
        )

    def open(self, host: str, path: str) -> tuple[int, dict, str]:
        """
        Fetch ``path`` on ``host`` as a browser does, signing in if the gate asks.

        A browser the gate already admits gets the app at once; otherwise the
        gate's redirect starts the handshake, which this completes.
        """
        status, headers, body = self.request(f"https://{host}{path}")
        if status != 302:
            return status, headers, body
        sign_in = headers["location"]
        assert urlsplit(sign_in).netloc == ADMIN, sign_in
        status, headers, _ = self.request(sign_in)
        assert status in {302, 303}, (status, headers)
        callback = headers["location"]
        assert urlsplit(callback).path == "/_hop3/auth/callback", callback
        status, headers, _ = self.request(callback)
        assert status in {302, 303}, (status, headers)
        assert headers["location"] == path
        return self.request(f"https://{host}{path}")

    def gate_cookie(self, host: str) -> str:
        jar = self.container.exec_run(["cat", self.jar]).output.decode()
        for line in jar.splitlines():
            fields = line.split("\t")
            if (
                len(fields) == 7
                and fields[0].endswith(host)
                and fields[5] == "__Host-hop3_gate"
            ):
                return fields[6]
        pytest.fail(f"no gate cookie for {host} in the jar:\n{jar}")


def answer(body: str) -> dict[str, str]:
    return json.loads(body)


def hop3(info: dict[str, Any], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["hop3", *args],
        env=cli_env(info),
        cwd=hermetic_cli_cwd(),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


@pytest.fixture(scope="module", params=["nginx", "caddy", "traefik"])
def gated(
    request: pytest.FixtureRequest,
    docker_client: docker.DockerClient,
    hop3_image: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[dict[str, Any]]:
    """A server on the given proxy with two gated apps and two accounts."""
    info = _start_hop3_container(
        docker_client,
        hop3_image,
        label=request.param,
        proxy=request.param,
        admin_domain=ADMIN,
    )
    try:
        for name, host, access in (
            ("notes", NOTES, 'require = "auth"\npublic-paths = ["/hook"]'),
            ("wiki", WIKI, 'require = "auth"\nrole = "viewer"'),
        ):
            result = deploy_flask_app(
                info,
                tmp_path_factory.mktemp(name),
                name,
                app_code=WHOAMI.replace("{name}", name),
                env_vars={"HOST_NAME": host},
                extra_files={"hop3.toml": f"[access]\n{access}\n"},
            )
            assert result.returncode == 0, (
                f"deploy of {name} failed\n{result.stdout}\n{result.stderr}\n"
                f"{_server_state(info)}"
            )
        for username, role in (
            ("mia", "member"),
            ("vera", "viewer"),
            ("otto", "member"),
        ):
            added = hop3(
                info,
                "user",
                "add",
                username,
                f"{username}@example.org",
                PASSWORD,
                "--role",
                role,
            )
            assert added.returncode == 0, f"{added.stdout}\n{added.stderr}"
        yield info
    finally:
        _stop_hop3_container(info)


@pytest.fixture(scope="module")
def mia(gated: dict[str, Any]) -> Browser:
    """A member's browser, signed in once: sign-ins are rate-limited per client."""
    return Browser(gated, "mia").sign_in("mia")


@pytest.fixture(scope="module")
def vera(gated: dict[str, Any]) -> Browser:
    """A viewer's browser, signed in once."""
    return Browser(gated, "vera").sign_in("vera")


@pytest.mark.e2e
class TestAccessGate:
    def test_an_anonymous_request_is_sent_to_sign_in(self, gated):
        status, headers, _ = Browser(gated, "anon").request(f"https://{NOTES}/page?x=1")

        assert status == 302
        login = urlsplit(headers["location"])
        assert (login.netloc, login.path) == (ADMIN, "/auth/login")
        assert parse_qs(login.query)["next"] == [f"https://{NOTES}/page?x=1"]

    def test_a_member_signs_in_and_reaches_the_app_as_itself(self, mia):
        status, _, body = mia.open(NOTES, "/page")

        assert status == 200
        seen = answer(body)
        assert (seen["app"], seen["path"], seen["user"], seen["role"]) == (
            "notes",
            "/page",
            "mia",
            "member",
        )

    def test_the_minimum_role_is_enforced(self, mia, vera):
        refused, _, text = mia.open(WIKI, "/")
        admitted, _, body = vera.open(WIKI, "/")

        assert refused == 403
        assert "needs the viewer role" in text
        assert admitted == 200
        assert answer(body)["user"] == "vera"

    def test_a_public_path_needs_no_sign_in(self, gated):
        status, _, body = Browser(gated, "anon-hook").request(f"https://{NOTES}/hook")

        assert status == 200
        assert answer(body)["app"] == "notes"

    def test_a_client_cannot_claim_an_identity(self, gated, mia):
        forged = {
            "X-Hop3-User": "admin",
            "X_Hop3_User": "admin",
            "X-Hop3-Role": "admin",
        }

        _, _, public = Browser(gated, "forger").request(
            f"https://{NOTES}/hook", headers=forged
        )
        mia.open(NOTES, "/")
        _, _, signed_in = mia.request(f"https://{NOTES}/page", headers=forged)

        assert (answer(public)["user"], answer(public)["role"]) == ("", "")
        assert (answer(signed_in)["user"], answer(signed_in)["role"]) == (
            "mia",
            "member",
        )

    def test_the_app_never_receives_the_gate_cookie(self, mia):
        mia.open(NOTES, "/")
        gate = mia.gate_cookie(NOTES)

        _, _, body = mia.request(
            f"https://{NOTES}/page",
            headers={"Cookie": f"theme=dark; __Host-hop3_gate={gate}"},
            jar=False,
        )

        assert answer(body)["user"] == "mia"
        assert answer(body)["cookie"] == "theme=dark"

    def test_a_gate_cookie_for_one_app_is_refused_by_another(self, mia):
        mia.open(NOTES, "/")
        gate = mia.gate_cookie(NOTES)

        status, headers, _ = mia.request(
            f"https://{WIKI}/",
            headers={"Cookie": f"__Host-hop3_gate={gate}"},
            jar=False,
        )

        assert status == 302
        assert urlsplit(headers["location"]).netloc == ADMIN

    def test_signing_out_of_hop3_signs_out_of_the_app(self, gated):
        browser = Browser(gated, "otto").sign_in("otto")
        status, _, _ = browser.open(NOTES, "/")
        assert status == 200

        logout, _, _ = browser.request(f"https://{ADMIN}/auth/logout", form={})
        assert logout in {302, 303}
        status, _, _ = browser.request(f"https://{NOTES}/page")

        assert status == 302

    def test_a_foreign_next_is_not_followed(self, mia):
        status, headers, _ = mia.continue_to("https://evil.example.com/steal")

        assert status in {302, 303}
        assert headers["location"] == "/auth/profile"

    def test_a_sign_in_link_works_only_in_the_browser_that_started_it(
        self, gated, mia, vera
    ):
        """Login CSRF: an attacker's sign-in link, opened in a victim's browser."""
        attacker = Browser(gated, "attacker")
        status, headers, _ = attacker.request(f"https://{NOTES}/trap")
        assert status == 302  # the gate gives the attacker's browser its state
        _, handoff, _ = vera.request(headers["location"])
        callback = handoff["location"]  # minted for vera, bound to that state

        status, _, body = mia.request(callback)

        assert status == 400
        assert "started in another browser" in body

    def test_a_member_gets_no_api_token(self, gated):
        """A gate account runs no command (ADR 061)."""
        got = hop3(gated, "auth", "get-token", "mia", PASSWORD)

        assert got.returncode != 0
        assert "is a member" in got.stdout + got.stderr

    def test_with_hop3_server_down_the_app_is_not_served(self, gated, mia):
        mia.open(NOTES, "/")
        container = gated["container"]
        container.exec_run("supervisorctl stop hop3-server")
        try:
            status, _, body = mia.request(f"https://{NOTES}/page")
        finally:
            container.exec_run("supervisorctl start hop3-server")
            _wait_for_server(container)

        assert status >= 500
        assert '"app"' not in body


SERVER_STATE = (
    "supervisorctl status; tail -n 30 /var/log/supervisor/supervisord.log "
    "/var/log/supervisor/hop3-server.log /var/log/supervisor/hop3-server_err.log"
)


@pytest.mark.e2e
def test_the_gated_fixture_check_passes(gated, tmp_path):
    """
    ``180-flask-gated``'s check.py, run as hop3-test runs it on a remote server.

    That fixture takes the gate into runs against servers with a real admin
    domain; proving its check here, on each proxy, means a failure there points
    at the server rather than at the check.
    """
    app_dir = tmp_path / "flask-gated"
    shutil.copytree(GATED_FIXTURE, app_dir)
    (app_dir / "ENV").write_text(f"HOST_NAME={GATED_FIXTURE_HOST}\n")
    init_git_repo(app_dir)
    deployed = deploy_app_dir(gated, app_dir, "flask-gated")
    assert deployed.returncode == 0, f"{deployed.stdout}\n{deployed.stderr}"

    container = gated["container"]
    container.put_archive("/tmp", _tar("check.py", (app_dir / "check.py").read_bytes()))
    result = container.exec_run([
        "/home/hop3/venv/bin/python",
        "/tmp/check.py",
        GATED_FIXTURE_HOST,
        "443",
    ])
    assert result.exit_code == 0, result.output.decode(errors="replace")


def _tar(name: str, content: bytes) -> bytes:
    """A one-file tar archive, the form ``put_archive`` takes."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _server_state(info: dict[str, Any]) -> str:
    """What the container's services say, collected before it is removed."""
    result = info["container"].exec_run(["sh", "-c", SERVER_STATE])
    return result.output.decode(errors="replace")


def _wait_for_server(container: Any, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = container.exec_run(
            "curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8000/"
        ).output.decode()
        if code in {"200", "302", "404"}:
            return
        time.sleep(1)
    pytest.fail("hop3-server did not come back after the outage test")
