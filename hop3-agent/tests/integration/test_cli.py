# Copyright (c) 2023-2024, Abilian SAS

import subprocess
import time
from os import environ
from pathlib import Path
from shutil import rmtree

import pytest

from hop3.core.app import App
from hop3.core.git import GitManager
from hop3.main import main as cli_main
from hop3.util import Abort

PATH = "/tmp/hop3"
environ["HOP3_HOME"] = PATH


@pytest.fixture(scope="session")
def hop3_home() -> Path:
    path = Path(PATH)

    # Clean up and prepare
    rmtree(path, ignore_errors=True)
    path.mkdir()
    (path / "tmp").mkdir()

    # Run setup
    cli_main(["setup"])

    assert (path / "apps").exists()
    return path

    # Clean up
    # rmtree(path, ignore_errors=True)


def test_setup_ssh(hop3_home):
    # Generate a key for this test
    ssh_file = hop3_home / "tmp" / "id_rsa"
    subprocess.run(["ssh-keygen", "-t", "rsa", "-N", "", "-f", ssh_file], check=True)

    # Run setup
    cli_main(["setup:ssh", str(ssh_file.with_suffix(".pub"))])
    authorized_keys = hop3_home / ".ssh" / "authorized_keys"
    assert authorized_keys.exists()


def test_help():
    cli_main(["help"])


def test_list_apps(hop3_home):
    cli_main(["apps"])


def test_inexistent_app(hop3_home):
    with pytest.raises(Abort):
        cli_main(["app", "inexistent"])


def test_lifecycle(hop3_home):
    app_name = f"test-app-{time.time()}"
    app = App(app_name)
    app.create()
    git_manager = GitManager(app)
    git_manager.setup_hook()
    git_manager.receive_pack()

    cli_main(["config", app_name])
