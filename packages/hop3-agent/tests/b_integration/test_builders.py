# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hop3.builders import GoBuilder, NodeBuilder, PythonBuilder, RubyBuilder

APPS = [
    ("010-flask-pip-wsgi", PythonBuilder),
    ("020-nodejs-express", NodeBuilder),
    ("flask-gunicorn-pip", PythonBuilder),
    ("flask-gunicorn-poetry", PythonBuilder),
    ("flask-pip-alt", PythonBuilder),
    ("golang-gin", GoBuilder),
    ("golang-minimal", GoBuilder),
    ("sinatra", RubyBuilder),
]


@pytest.mark.parametrize(("app_name", "builder_cls"), APPS)
def test_builders(tmp_path, app_name, builder_cls):
    # Temp
    Path("/tmp/hop3/envs").mkdir(exist_ok=True, parents=True)

    # Copy app to src directory
    app_path = tmp_path / app_name
    app_path.mkdir()
    shutil.copytree(f"apps/test-apps/{app_name}", app_path / "src")

    builder = builder_cls(app_name, app_path)
    assert builder.accept()

    builder.build()
    # Nothing to assert, builder would raise an exception if something went wrong
