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


class TestNodeVersionDeclaration:
    """Guard rails for the `[build].node-version` field bridging
    through to NODE_VERSION (consumed by install_node + nodeenv)."""

    def _ctx(self, app_path, app_config):
        from hop3.core.protocols import BuildContext

        src = app_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "package.json").write_text("{}")
        return BuildContext(
            app_name="myapp", source_path=src, app_config=app_config
        )

    def test_declared_version_returned(self, app_path):
        ctx = self._ctx(
            app_path,
            app_config={"hop3_config": {"build": {"node-version": "22"}}},
        )
        tc = NodeToolchain(ctx)
        assert tc._get_declared_node_version() == "22"

    def test_not_declared_returns_none(self, app_path):
        ctx = self._ctx(app_path, app_config={"hop3_config": {"build": {}}})
        tc = NodeToolchain(ctx)
        assert tc._get_declared_node_version() is None

    def test_missing_hop3_config_returns_none(self, app_path):
        ctx = self._ctx(app_path, app_config={})
        tc = NodeToolchain(ctx)
        assert tc._get_declared_node_version() is None

    def test_non_dict_build_section_returns_none(self, app_path):
        ctx = self._ctx(
            app_path, app_config={"hop3_config": {"build": "not a dict"}}
        )
        tc = NodeToolchain(ctx)
        assert tc._get_declared_node_version() is None

    def test_version_coerced_to_string(self, app_path):
        """Version may be declared as a number in TOML; coerce to str
        so it can flow through env-var plumbing."""
        ctx = self._ctx(
            app_path,
            app_config={"hop3_config": {"build": {"node-version": 22}}},
        )
        tc = NodeToolchain(ctx)
        assert tc._get_declared_node_version() == "22"


class TestRustToolchainBuild:
    """Guard rails for the two rust.py fixes: raise on cargo failure
    (was: silently continue with a fake artifact, leaving a useless
    "target/release/<bin>: No such file" at runtime) and honour
    `[build].build` from hop3.toml (other toolchains already do)."""

    def _spec_with_cargo_result(
        self, app_path, monkeypatch, returncode, app_config=None
    ):
        import subprocess

        from hop3.core.protocols import BuildContext
        from hop3.toolchains import rust as rust_module

        (app_path / "src" / "Cargo.toml").write_text("[package]\nname = 'x'")
        ctx = BuildContext(
            app_name="x",
            source_path=app_path / "src",
            app_config=app_config or {},
        )
        toolchain = RustToolchain(ctx)

        captured: dict[str, str] = {}

        def fake_shell(self, command, cwd="", **kwargs):
            captured["command"] = command
            return subprocess.CompletedProcess(
                args=command, returncode=returncode, stdout="", stderr=""
            )

        monkeypatch.setattr(RustToolchain, "shell", fake_shell)
        monkeypatch.setattr(rust_module, "find_cargo", lambda: "/usr/bin/cargo")
        # Stub artifact creation so we don't poke the filesystem.
        monkeypatch.setattr(
            RustToolchain,
            "_make_build_artifact",
            lambda self, kind: object(),
        )
        return toolchain, captured

    def test_raises_on_cargo_failure(self, app_path, monkeypatch):
        toolchain, _ = self._spec_with_cargo_result(
            app_path, monkeypatch, returncode=101
        )
        with pytest.raises(RuntimeError, match="Rust compilation failed"):
            toolchain.build()

    def test_succeeds_on_cargo_zero(self, app_path, monkeypatch):
        toolchain, _ = self._spec_with_cargo_result(
            app_path, monkeypatch, returncode=0
        )
        # Should not raise; returns the stubbed artifact object.
        assert toolchain.build() is not None

    def test_custom_build_command_honoured(self, app_path, monkeypatch):
        """[build].build = 'cargo build --release --features sqlite' should
        override the default `cargo build --release`."""
        toolchain, captured = self._spec_with_cargo_result(
            app_path,
            monkeypatch,
            returncode=0,
            app_config={
                "hop3_config": {
                    "build": {
                        "build": "cargo build --release --features sqlite,postgresql"
                    }
                }
            },
        )
        toolchain.build()
        assert captured["command"] == (
            "cargo build --release --features sqlite,postgresql"
        )

    def test_default_command_when_no_override(self, app_path, monkeypatch):
        toolchain, captured = self._spec_with_cargo_result(
            app_path, monkeypatch, returncode=0
        )
        toolchain.build()
        assert captured["command"] == "/usr/bin/cargo build --release"
