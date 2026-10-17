# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
`hop3-test run --recipes published` tests the catalog the server publishes.

The tests come from the server's extracted recipes, and each app is installed
with `hop3 catalog install`, then upgraded, the way an operator does it.
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import tarfile
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner
from hop3_testing.apps import deployment
from hop3_testing.apps.catalog import AppSource
from hop3_testing.apps.deployment import DeploymentSession
from hop3_testing.catalog import published
from hop3_testing.catalog.published import (
    PublishedCatalogError,
    published_tests,
    select_ids,
)
from hop3_testing.cli import cli

if TYPE_CHECKING:
    from pathlib import Path

_INDEX = {
    "format": 1,
    "serial": 7,
    "apps": [
        {"id": "bookstack", "status": "golden"},
        {"id": "isso", "status": "beta"},
        {"id": "gitea", "status": "golden"},
    ],
}

_HOP3_TOML = """\
[metadata]
id = "{id}"

[build]
builder = "native"

[test]
priority = "P1"
covers = ["php"]

[[test.validations]]
path = "/"
status = 200
contains = "{id}"
"""


def _tarball(ids: list[str]) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for app_id in ids:
            data = _HOP3_TOML.format(id=app_id).encode()
            info = tarfile.TarInfo(f"{app_id}/hop3.toml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return base64.b64encode(buf.getvalue()).decode()


class _Server:
    """Answers the reads a published run makes on the target."""

    def __init__(self) -> None:
        self.commands: list = []

    def cli_env(self) -> dict[str, str]:
        return {}

    def exec_run(self, cmd):
        self.commands.append(cmd)
        if cmd == ["cat", "/home/hop3/catalog/index.json"]:
            return 0, json.dumps(_INDEX), ""
        tar = cmd[-1]
        ids = [i for i in ("bookstack", "gitea", "isso") if f" {i}" in tar]
        return 0, _tarball(ids), ""


@pytest.fixture
def refreshed(monkeypatch):
    calls: list = []

    def run(cmd, **_kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "Catalog refreshed to serial 7.", "")

    monkeypatch.setattr(published.subprocess, "run", run)
    return calls


def test_the_tests_are_the_servers_recipes(tmp_path, refreshed):
    server = _Server()

    tests = published_tests(server, ("golden",), (), tmp_path)

    assert refreshed == [["hop3", "catalog", "refresh"]]
    assert [t.name for t in tests] == ["bookstack", "gitea"]
    assert [t.catalog_id for t in tests] == ["bookstack", "gitea"]
    assert tests[0].app_path == tmp_path / "bookstack"
    assert tests[0].validations[0].expect.contains == "bookstack"


def test_a_failed_refresh_stops_the_run(tmp_path, monkeypatch):
    def run(cmd, **_kw):
        return subprocess.CompletedProcess(cmd, 0, "", "Catalog refresh failed: 404")

    monkeypatch.setattr(published.subprocess, "run", run)

    with pytest.raises(PublishedCatalogError, match="404"):
        published_tests(_Server(), ("golden",), (), tmp_path)


def test_selection_by_status_and_name():
    assert select_ids(_INDEX, ("golden", "beta"), ()) == ["bookstack", "gitea", "isso"]
    assert select_ids(_INDEX, ("beta",), ()) == ["isso"]
    assert select_ids(_INDEX, ("golden",), ("gitea",)) == ["gitea"]


def test_a_name_the_catalog_does_not_publish_is_an_error():
    with pytest.raises(PublishedCatalogError, match="wekan"):
        select_ids(_INDEX, ("golden",), ("gitea", "wekan"))


def test_a_selection_matching_nothing_is_an_error():
    with pytest.raises(PublishedCatalogError, match="no entry"):
        select_ids(_INDEX, ("beta",), ("gitea",))


def test_alpha_is_refused_with_the_reason(monkeypatch):
    monkeypatch.delenv("HOP3_HOST", raising=False)

    result = CliRunner().invoke(
        cli, ["run", "--docker", "--recipes", "published", "--status", "alpha"]
    )

    assert result.exit_code == 1
    assert "alpha is not published" in result.output
    assert "golden and beta" in result.output


def _session(tmp_path: Path, hop3_toml: str = "") -> DeploymentSession:
    (tmp_path / "hop3.toml").write_text(hop3_toml)
    app = AppSource(name="bookstack", path=tmp_path, catalog_id="bookstack")
    return DeploymentSession(app, _Server(), app_name="bookstack-1")


def test_the_first_deploy_installs_from_the_catalog(tmp_path):
    session = _session(tmp_path)

    assert session._deploy_command() == [
        "hop3", "catalog", "install", "bookstack",
        "--app", "bookstack-1", "--domain", "bookstack-1.test.local",
    ]  # fmt: skip


def test_the_redeploy_upgrades_the_installed_app(tmp_path):
    session = _session(tmp_path)
    session.deployed = True

    assert session._deploy_command() == [
        "hop3", "app", "upgrade", "--app", "bookstack-1",
    ]  # fmt: skip


def test_a_recipe_naming_its_host_keeps_it(tmp_path):
    session = _session(tmp_path, '[env]\nHOST_NAME = "books.example.com"\n')

    assert "--domain" not in session._deploy_command()


def test_cleanup_after_a_refused_install_reports_nothing(tmp_path, monkeypatch):
    """The install was refused, so no app exists: nothing to destroy, nothing leaked."""

    def run(cmd, **_kw):
        return subprocess.CompletedProcess(
            cmd, 2, "", "Failed to destroy app: App 'bookstack-1' not found."
        )

    monkeypatch.setattr(deployment.subprocess, "run", run)

    assert _session(tmp_path).cleanup() is None
