# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

import pytest

from hop3.toolchains import (
    ClojureToolchain,
    NodeToolchain,
    PythonToolchain,
    RubyToolchain,
    RustToolchain,
)


@pytest.fixture
def app_path(tmp_path):
    app_path = tmp_path / "myapp"
    (app_path / "src").mkdir(parents=True)
    return app_path


def test_python_toolchain(app_path):
    (app_path / "src" / "requirements.txt").write_text("flask")
    toolchain = PythonToolchain("myapp", app_path)
    assert toolchain.accept()


def test_node_toolchain(app_path):
    (app_path / "src" / "package.json").write_text("{}")
    toolchain = NodeToolchain("myapp", app_path)
    assert toolchain.accept()


def test_rust_toolchain(app_path):
    (app_path / "src" / "Cargo.toml").write_text("[package]\nname = 'myapp'")
    toolchain = RustToolchain("myapp", app_path)
    assert toolchain.accept()


def test_ruby_toolchain(app_path):
    (app_path / "src" / "Gemfile").write_text(
        "source 'https://rubygems.org'\ngem 'sinatra'"
    )
    toolchain = RubyToolchain("myapp", app_path)
    assert toolchain.accept()


def test_clojure_toolchain(app_path):
    (app_path / "src" / "deps.edn").write_text(
        '{:deps {org.clojure/clojure {:mvn/version "1.10.1"}}}'
    )
    toolchain = ClojureToolchain("myapp", app_path)
    assert toolchain.accept()
