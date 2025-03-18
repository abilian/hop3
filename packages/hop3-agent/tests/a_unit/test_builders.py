# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

import pytest

from hop3.builders import ClojureBuilder, NodeBuilder, PythonBuilder, RubyBuilder
from hop3.builders.rust import RustBuilder


@pytest.fixture
def app_path(tmp_path):
    app_path = tmp_path / "myapp"
    (app_path / "src").mkdir(parents=True)
    return app_path


def test_python_builder(app_path):
    (app_path / "src" / "requirements.txt").write_text("flask")
    builder = PythonBuilder("myapp", app_path)
    assert builder.accept()


def test_node_builder(app_path):
    (app_path / "src" / "package.json").write_text("{}")
    builder = NodeBuilder("myapp", app_path)
    assert builder.accept()


def test_rust_builder(app_path):
    (app_path / "src" / "Cargo.toml").write_text("[package]\nname = 'myapp'")
    builder = RustBuilder("myapp", app_path)
    assert builder.accept()


def test_ruby_builder(app_path):
    (app_path / "src" / "Gemfile").write_text(
        "source 'https://rubygems.org'\ngem 'sinatra'"
    )
    builder = RubyBuilder("myapp", app_path)
    assert builder.accept()


def test_clojure_builder(app_path):
    (app_path / "src" / "deps.edn").write_text(
        '{:deps {org.clojure/clojure {:mvn/version "1.10.1"}}}'
    )
    builder = ClojureBuilder("myapp", app_path)
    assert builder.accept()
