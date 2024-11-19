# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

import os
import shutil
from pathlib import Path

from devtools import debug
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


def test_python_builder(tmp_path):
    debug(os.getcwd())
    app_path = tmp_path / "myapp"
    shutil.copytree("apps/test-apps/010-flask-pip-wsgi", app_path)
    Path("/private/tmp/hop3/envs").mkdir(exist_ok=True, parents=True)
    builder = PythonBuilder("myapp", app_path)
    assert builder.accept()
    builder.build()
