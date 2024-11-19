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
    Path("/private/tmp/hop3/envs").mkdir(exist_ok=True, parents=True)

    app_path = tmp_path / app_name
    shutil.copytree(f"apps/test-apps/{app_name}", app_path)
    builder = builder_cls(app_name, app_path)
    assert builder.accept()
    builder.build()
