# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: a protected server takes a change only when the operator named it
(ADR 042, rule D).

The server is set up the way the docs tell an operator to: `PROTECTED = true`
in `hop3-server.toml`, then a restart. The CLI runs from a config home of its
own, with a context named for the server and a checkout bound to it, so each
check goes through the CLI's own resolution of where a command is sent:

- the checkout's binding picks the server: a change is refused, and nothing
  changes;
- `-c <context>` names it: the CLI asks for the app's name, typed at a
  terminal, then the change is made;
- a read-only command goes through from the binding.
"""

from __future__ import annotations

import os
import pty
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from .conftest import (
    _start_hop3_container,
    _stop_hop3_container,
    _wait_for_host_port,
    deploy_flask_app,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import docker

APP = "guarded"
CONTEXT = "prod"
KEY = "PROTECTED_E2E"
#: The CLI's exit code when a confirmation was not given.
CONFIRMATION_DECLINED = 10


@pytest.fixture(scope="module")
def protected(
    docker_client: docker.DockerClient,
    hop3_image: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[dict[str, Any]]:
    """A server with one app, protected after the deploy, and a CLI bound to it."""
    info = _start_hop3_container(docker_client, hop3_image, label="protected")
    try:
        deployed = deploy_flask_app(info, tmp_path_factory.mktemp("app"), APP)
        assert deployed.returncode == 0, f"{deployed.stdout}\n{deployed.stderr}"
        _protect(info)

        home = tmp_path_factory.mktemp("cli-home")
        checkout = tmp_path_factory.mktemp("checkout")
        (checkout / "hop3.toml").write_text(f'[metadata]\nid = "{APP}"\n')
        info["cli"] = {"home": home, "checkout": checkout}
        added = hop3(info, "context", "add", CONTEXT, "--server", info["api_url"])
        assert added.returncode == 0, added.stderr
        bound = hop3(info, "context", "use", CONTEXT, "-y", cwd=checkout)
        assert bound.returncode == 0, bound.stderr
        yield info
    finally:
        _stop_hop3_container(info)


def _protect(info: dict[str, Any]) -> None:
    """`PROTECTED = true` in hop3-server.toml, then restart the server."""
    container = info["container"]
    # First line: a top-level key appended after a [table] would land in it.
    result = container.exec_run([
        "sh",
        "-c",
        (
            "sed -i '1i PROTECTED = true' /home/hop3/hop3-server.toml "
            "&& supervisorctl restart hop3-server"
        ),
    ])
    assert result.exit_code == 0, result.output.decode()
    _wait_for_host_port(f"{info['api_url']}/", info["label"])


def _cli_env(info: dict[str, Any]) -> dict[str, str]:
    """The CLI's own config home; the server is reached only through a context."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("HOP3_") or k == "HOP3_SECRET_KEY"
    }
    env["HOP3_CONFIG_DIR"] = str(info["cli"]["home"])
    env["HOP3_API_TOKEN"] = info["api_token"]
    return env


def hop3(
    info: dict[str, Any], *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess:
    """`hop3 …` from ``cwd`` (the config home by default: no checkout there)."""
    return subprocess.run(
        ["hop3", *args],
        env=_cli_env(info),
        cwd=cwd or info["cli"]["home"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def hop3_at_a_terminal(info: dict[str, Any], *args: str, typed: str) -> tuple[int, str]:
    """`hop3 …` with a terminal on stdin; ``typed`` answers its question."""
    master, slave = pty.openpty()
    process = subprocess.Popen(
        ["hop3", *args],
        env=_cli_env(info),
        cwd=info["cli"]["home"],
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    os.close(slave)
    try:
        # The terminal holds the line until the CLI asks, after the refusal.
        os.write(master, f"{typed}\n".encode())
        output, _ = process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
    finally:
        os.close(master)
    return process.returncode, output


def _stored_value(info: dict[str, Any]) -> list[str]:
    """The lines `env get` prints for KEY, read with the server named and --yes."""
    shown = hop3(info, "-c", CONTEXT, "env", "get", "--app", APP, KEY, "--yes")
    assert shown.returncode == 0, f"{shown.stdout}\n{shown.stderr}"
    return [line.strip() for line in shown.stdout.splitlines()]


@pytest.mark.e2e
class TestProtectedServer:
    def test_a_change_chosen_by_the_binding_is_refused(self, protected):
        refused = hop3(
            protected,
            "env",
            "set",
            "--app",
            APP,
            f"{KEY}=from-binding",
            cwd=protected["cli"]["checkout"],
        )

        assert refused.returncode != 0
        output = refused.stdout + refused.stderr
        assert "This server is protected" in output, output
        assert "name the server" in output, output
        assert "from-binding" not in _stored_value(protected)

    def test_a_named_server_asks_for_the_apps_name_before_changing(self, protected):
        code, output = hop3_at_a_terminal(
            protected,
            "-c",
            CONTEXT,
            "env",
            "set",
            "--app",
            APP,
            f"{KEY}=named",
            typed=APP,
        )

        assert code == 0, output
        assert f"Type the app's name ({APP})" in output, output
        assert "named" in _stored_value(protected)

    def test_a_wrong_name_changes_nothing(self, protected):
        code, output = hop3_at_a_terminal(
            protected,
            "-c",
            CONTEXT,
            "env",
            "set",
            "--app",
            APP,
            f"{KEY}=mistyped",
            typed="not-the-app",
        )

        assert code == CONFIRMATION_DECLINED, output
        assert "does not match" in output, output
        assert "mistyped" not in _stored_value(protected)

    def test_a_read_only_command_goes_through_from_the_binding(self, protected):
        listed = hop3(protected, "app", "list", cwd=protected["cli"]["checkout"])

        assert listed.returncode == 0, f"{listed.stdout}\n{listed.stderr}"
        assert APP in listed.stdout
