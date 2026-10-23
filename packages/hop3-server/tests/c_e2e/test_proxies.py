# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: the same app, served through each reverse proxy Hop3 supports.

Every other e2e runs on nginx. Caddy and Traefik each had a plugin and a place
in the image, and no test had ever selected them. When one first did, Caddy
failed validation on every deploy and Traefik routed nothing on port 80. Each
proxy now gets the same requests, sent to its own ports by hostname:

* plain HTTP when the app allows it, and `.git` refused;
* the redirect to HTTPS by default, and the app over HTTPS;
* a PHP app on its php-fpm pool, where the proxy speaks FastCGI, and the
  paths under its tree the proxy must never answer;
* a static app, whose directories are served under their slash;
* a WAF-enabled app, where the proxy can front the WAF.

Where a proxy cannot do something, the deploy must be refused before anything
is built, and it must say why. The proxies that can do it run the same deploy
as the positive control.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from .conftest import (
    ALLOW_PLAIN_HTTP,
    _start_hop3_container,
    _stop_hop3_container,
    deploy_app_dir,
    deploy_flask_app,
    init_git_repo,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    import docker

PHP_FIXTURE = (
    Path(__file__).parents[4] / "apps" / "test-apps-procfile" / "060-php-hello"
)

STATIC_FIXTURE = PHP_FIXTURE.with_name("000-static")

#: What each proxy declares it can do (``BaseProxy`` capabilities).
SPEAKS_FASTCGI = {"nginx": True, "caddy": True, "traefik": False}
SERVES_FILES = {"nginx": True, "caddy": True, "traefik": False}
FRONTS_WAF = {"nginx": True, "caddy": False, "traefik": False}

#: Written into files the proxy must never serve; absent from every answer.
SECRET = "hop3-must-not-serve-this"


@pytest.fixture(scope="module", params=["nginx", "caddy", "traefik"])
def proxied(
    request: pytest.FixtureRequest,
    docker_client: docker.DockerClient,
    hop3_image: str,
) -> Iterator[dict[str, Any]]:
    """A hop3 container whose reverse proxy is the parameter."""
    info = _start_hop3_container(
        docker_client, hop3_image, label=request.param, proxy=request.param
    )
    try:
        yield info
    finally:
        _stop_hop3_container(info)


def http_get(info: dict[str, Any], host: str, path: str = "/") -> httpx.Response:
    return httpx.get(
        info["http_base"] + path,
        headers={"Host": host},
        timeout=5,
        follow_redirects=False,
    )


def https_get(info: dict[str, Any], host: str, path: str = "/") -> tuple[int, str]:
    """
    GET over the proxy's TLS listener, by SNI, from inside the container.

    The path is sent as written (``--path-as-is``), so a test can send the
    spellings a client would use to slip past a path rule.
    """
    result = info["container"].exec_run(
        f"curl -sk --path-as-is --resolve {host}:443:127.0.0.1 "
        f"-w '\\n%{{http_code}}' https://{host}{path}"
    )
    body, _, status = result.output.decode(errors="replace").rpartition("\n")
    return int(status), body


def https_head(info: dict[str, Any], host: str, path: str) -> tuple[int, str]:
    """Status and Location of a GET over TLS, the redirect not followed."""
    result = info["container"].exec_run(
        f"curl -sk -o /dev/null --resolve {host}:443:127.0.0.1 "
        f"-w '%{{http_code}} %header{{location}}' 'https://{host}{path}'"
    )
    status, _, location = result.output.decode(errors="replace").partition(" ")
    return int(status), location.strip()


def eventually(probe: Callable[[], Any], accept: Callable[[Any], bool]) -> Any:
    """The probe's first accepted answer within 30s (proxies apply config async)."""
    deadline = time.monotonic() + 30
    answer = None
    while time.monotonic() < deadline:
        try:
            answer = probe()
        except httpx.HTTPError as e:
            answer = e
        if accept(answer):
            return answer
        time.sleep(1)
    return answer


def deployed(result: Any) -> None:
    assert result.returncode == 0, (
        f"deploy failed\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


def refused(result: Any, reason: str) -> None:
    output = result.stdout + result.stderr
    assert result.returncode != 0, f"deploy should have been refused:\n{output}"
    # The CLI wraps its messages at the terminal width.
    assert reason in " ".join(output.split()), (
        f"refusal does not say {reason!r}:\n{output}"
    )


def ok_with(text: str) -> Callable[[Any], bool]:
    return lambda r: (
        isinstance(r, httpx.Response) and r.status_code == 200 and (text in r.text)
    )


@pytest.mark.e2e
class TestProxies:
    def test_plain_http_when_the_app_allows_it(self, proxied, test_app_dir, request):
        proxy = proxied["proxy"]
        host = f"plain-{proxy}.test.local"
        request.node.hop3_container = proxied["container"]
        request.node.hop3_app = "plain"

        deployed(
            deploy_flask_app(
                proxied,
                test_app_dir,
                "plain",
                env_vars={"HOST_NAME": host},
                extra_files={"hop3.toml": ALLOW_PLAIN_HTTP},
            )
        )

        response = eventually(
            lambda: http_get(proxied, host), ok_with("Hello from Flask!")
        )
        assert ok_with("Hello from Flask!")(response), response
        assert http_get(proxied, host, "/.git/config").status_code == 403

    def test_https_by_default(self, proxied, test_app_dir, request):
        proxy = proxied["proxy"]
        host = f"secure-{proxy}.test.local"
        request.node.hop3_container = proxied["container"]
        request.node.hop3_app = "secure"

        deployed(
            deploy_flask_app(
                proxied, test_app_dir, "secure", env_vars={"HOST_NAME": host}
            )
        )

        status, body = eventually(
            lambda: https_get(proxied, host), lambda answer: answer[0] == 200
        )
        assert (status, body) == (200, "Hello from Flask!")
        redirect = http_get(proxied, host)
        assert redirect.status_code in {301, 308}
        assert redirect.headers["location"] == f"https://{host}/"

    def test_a_php_app_on_its_fpm_pool(self, proxied, tmp_path, request):
        proxy = proxied["proxy"]
        host = f"php-{proxy}.test.local"
        request.node.hop3_container = proxied["container"]
        request.node.hop3_app = "php"
        app_dir = tmp_path / "php"
        shutil.copytree(PHP_FIXTURE, app_dir)
        (app_dir / "ENV").write_text(f"HOST_NAME={host}\n")
        # What PHP apps keep in the tree they serve, behind an .htaccess
        # that nginx and Caddy never read.
        (app_dir / "hop3.toml").write_text('[proxy]\ndeny = ["/data"]\n')
        (app_dir / "data").mkdir()
        (app_dir / "data" / "secret.txt").write_text(SECRET)
        (app_dir / "data" / "run.php").write_text(f"<?php echo '{SECRET}';\n")
        (app_dir / "datasheet.txt").write_text("a public sheet\n")
        (app_dir / ".env").write_text(f"APP_KEY={SECRET}\n")
        (app_dir / ".hidden").mkdir()
        (app_dir / ".hidden" / "run.php").write_text(f"<?php echo '{SECRET}';\n")
        init_git_repo(app_dir)

        result = deploy_app_dir(proxied, app_dir, "php")

        if not SPEAKS_FASTCGI[proxy]:
            refused(result, f"speaks fastcgi, which {proxy} cannot proxy")
            return
        deployed(result)
        status, body = eventually(
            lambda: https_get(proxied, host), lambda answer: answer[0] == 200
        )
        assert status == 200
        assert "sapi: fpm-fcgi" in body
        status, body = https_get(proxied, host, "/no/such/page")
        assert (status, "front controller handled: /no/such/page" in body) == (
            200,
            True,
        )
        status, body = https_get(proxied, host, "/assets/style.css")
        assert (status, "font-family" in body) == (200, True)

        for path in (
            "/data",
            "/data/secret.txt",
            "/data/run.php",
            "//data/secret.txt",
            "/d%61ta/secret.txt",
            "/assets/../data/secret.txt",
            "/.env",
            "/.hidden/run.php",
        ):
            status, body = https_get(proxied, host, path)
            assert (status, SECRET in body) == (404, False), (path, body)
        # The rule is the path and what is beneath it, not every name that
        # starts with the same letters; and discovery under /.well-known
        # still reaches the app.
        status, body = https_get(proxied, host, "/datasheet.txt")
        assert (status, body.strip()) == (200, "a public sheet")
        status, body = https_get(proxied, host, "/.well-known/caldav")
        assert (status, "front controller handled: /.well-known/caldav" in body) == (
            200,
            True,
        )

    def test_a_directory_is_served_under_its_slash(self, proxied, tmp_path, request):
        """
        `/docs` redirects to `/docs/`, where its index.html's relative links
        resolve inside it; serving the index at `/docs` resolved them against
        the parent.
        """
        proxy = proxied["proxy"]
        host = f"static-{proxy}.test.local"
        request.node.hop3_container = proxied["container"]
        request.node.hop3_app = "static"
        app_dir = tmp_path / "static"
        shutil.copytree(STATIC_FIXTURE, app_dir)
        (app_dir / "ENV").write_text(f"HOST_NAME={host}\n")
        (app_dir / "public" / "docs").mkdir()
        (app_dir / "public" / "docs" / "index.html").write_text(
            '<a href="page.html">the docs index</a>\n'
        )
        init_git_repo(app_dir)

        result = deploy_app_dir(proxied, app_dir, "static")

        if not SERVES_FILES[proxy]:
            refused(result, f"and {proxy} serves no files")
            return
        deployed(result)
        status, body = eventually(
            lambda: https_get(proxied, host, "/docs/"),
            lambda answer: answer[0] == 200,
        )
        assert (status, "the docs index" in body) == (200, True)
        # Relative, so a client behind a port mapping can follow it.
        for path, location in (("/docs", "/docs/"), ("/docs?x=1", "/docs/?x=1")):
            assert https_head(proxied, host, path) in {
                (301, location),
                (308, location),
            }, path
        status, _ = https_get(proxied, host, "/")
        assert status == 200

    def test_a_waf_enabled_app(self, proxied, test_app_dir, request):
        proxy = proxied["proxy"]
        host = f"waf-{proxy}.test.local"
        request.node.hop3_container = proxied["container"]
        request.node.hop3_app = "waf"

        result = deploy_flask_app(
            proxied,
            test_app_dir,
            "waf",
            env_vars={"HOST_NAME": host},
            extra_files={"hop3.toml": "[waf]\nenabled = true\n" + ALLOW_PLAIN_HTTP},
        )

        if not FRONTS_WAF[proxy]:
            refused(result, f"this server's proxy ({proxy}) cannot route an app")
            assert "Build successful" not in result.stdout + result.stderr
            return
        deployed(result)
        response = eventually(
            lambda: http_get(proxied, host), ok_with("Hello from Flask!")
        )
        assert ok_with("Hello from Flask!")(response), response
