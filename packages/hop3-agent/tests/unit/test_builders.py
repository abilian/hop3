# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

from hop3.builders import ClojureBuilder, NodeBuilder, PythonBuilder, RubyBuilder
from hop3.builders.rust import RustBuilder


def test_python_builder(tmp_path):
    app_path = tmp_path / "myapp"
    app_path.mkdir()
    (app_path / "requirements.txt").write_text("flask")
    builder = PythonBuilder("myapp", app_path)
    assert builder.accept()


def test_node_builder(tmp_path):
    app_path = tmp_path / "myapp"
    app_path.mkdir()
    (app_path / "package.json").write_text("{}")
    builder = NodeBuilder("myapp", app_path)
    assert builder.accept()


def test_rust_builder(tmp_path):
    app_path = tmp_path / "myapp"
    app_path.mkdir()
    (app_path / "Cargo.toml").write_text("[package]\nname = 'myapp'")
    builder = RustBuilder("myapp", app_path)
    assert builder.accept()


def test_ruby_builder(tmp_path):
    app_path = tmp_path / "myapp"
    app_path.mkdir()
    (app_path / "Gemfile").write_text("source 'https://rubygems.org'\ngem 'sinatra'")
    builder = RubyBuilder("myapp", app_path)
    assert builder.accept()


def test_clojure_builder(tmp_path):
    app_path = tmp_path / "myapp"
    app_path.mkdir()
    (app_path / "deps.edn").write_text(
        '{:deps {org.clojure/clojure {:mvn/version "1.10.1"}}}'
    )
    builder = ClojureBuilder("myapp", app_path)
    assert builder.accept()
