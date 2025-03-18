# Copyright (c) 2023-2024, Abilian SAS
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from shutil import rmtree
from typing import TYPE_CHECKING

import pytest

from hop3 import config
from hop3.core.git import GitManager
from hop3.main import main as cli_main
from hop3.orm import App, AppRepository, get_session_factory
from hop3.util import Abort
from hop3.util.console import console

if TYPE_CHECKING:
    from collections.abc import Generator



@pytest.fixture(scope="session")
def hop3_home() -> Generator[Path]:
    path = config.HOP3_ROOT

    # Clean up and prepare
    rmtree(path, ignore_errors=True)
    path.mkdir()
    (path / "tmp").mkdir()

    # Run setup
    cli_main(["setup"])

    assert (path / "apps").exists()
    yield path  # noqa: PT022

    # Don't clean up to be able to debug


def test_setup_ssh(hop3_home) -> None:
    # Generate a key for this test
    ssh_file = hop3_home / "tmp" / "id_rsa"
    subprocess.run(["ssh-keygen", "-t", "rsa", "-N", "", "-f", ssh_file], check=True)

    # Run setup
    cli_main(["setup:ssh", str(ssh_file.with_suffix(".pub"))])
    authorized_keys = hop3_home / ".ssh" / "authorized_keys"
    assert authorized_keys.exists()


def test_help() -> None:
    cli_main(["help"])


def test_list_apps(hop3_home) -> None:
    cli_main(["apps"])


def test_inexistent_app(hop3_home) -> None:
    with pytest.raises(Abort):
        cli_main(["app", "inexistent"])


def test_lifecycle(hop3_home) -> None:
    app_name = f"test-app-{time.time()}"
    app = App(name=app_name)
    app.create()
    assert app.app_path.exists()

    create_dummy_app(app)

    session_factory = get_session_factory()
    with session_factory() as db_session:
        app_repo = AppRepository(session=db_session)
        app_repo.add(app, auto_commit=True)

    cli_main(["config:list", app_name])
    # assert not console.output()

    cli_main(["config:set", app_name, "XXX=xyz"])
    assert app_name in console.output()

    cli_main(["config:get", app_name, "XXX"])
    assert "xyz" in console.output()

    cli_main(["config:unset", app_name, "XXX"])
    assert "xyz" not in console.output()
    assert app_name in console.output()

    # cli_main(["logs", app_name])

    cli_main(["apps"])
    assert app_name in console.output()

    assert len(list((hop3_home / "uwsgi-available").iterdir())) == 1

    # Scaling
    cli_main(["ps", app_name])
    assert "web:1" in console.output()

    cli_main(["ps:scale", app_name, "web=2"])
    assert "web.2" in console.output()

    cli_main(["ps", app_name])
    assert "web:2" in console.output()

    cli_main(["ps:scale", app_name, "web=1"])
    assert "web" in console.output()

    cli_main(["ps", app_name])
    assert "web:1" in console.output()

    cli_main(["run", app_name, "/bin/pwd"])
    assert app_name in console.output()

    cli_main(["start", app_name])

    cli_main(["stop", app_name])

    cli_main(["destroy", app_name])

    cli_main(["apps"])
    assert app_name not in console.output()

    assert not (hop3_home / "apps" / app_name).exists()
    assert len(list((hop3_home / "uwsgi-available").iterdir())) == 0


def create_dummy_app(app: App) -> None:
    # This creates the app (bypassing the CLI)
    # Using a pre-existing git repository (./bare-git)
    # There are two files in it: Procfile and requirements.txt

    git_manager = GitManager(app)
    git_manager.setup_hook()

    cmd = [
        "rsync",
        "-a",
        "--delete",
        str(Path(__file__).parent / "bare-git") + "/",
        str(app.repo_path) + "/",
    ]
    subprocess.run(cmd, check=True)

    shutil.rmtree(app.src_path)
    git_manager.clone()
