# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Detection (`accept()`) and pure build-decision logic for language toolchains.

These lock down two things that the deploy path relies on:

1. Each toolchain's ``accept()`` fires for its own marker file(s) and
   does NOT fire for another language's project (no false-positive detection,
   which would route an app to the wrong builder).
2. The pure build helpers on the base class (Procfile worker parsing, custom
   build-command extraction, BuildArtifact shape) reflect their inputs.

Legacy construction is ``Toolchain("name", app_path)`` with sources under
``app_path/src`` (see test_builders.py / test_static_toolchain.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.protocols import BuildContext
from hop3.toolchains import (
    ClojureToolchain,
    DotNetToolchain,
    ElixirToolchain,
    GenericToolchain,
    GoToolchain,
    JavaToolchain,
    NodeToolchain,
    PHPToolchain,
    PythonToolchain,
    RubyToolchain,
    RustToolchain,
)

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.toolchains._base import LanguageToolchain


def _app(tmp_path: Path) -> Path:
    """Create an app dir with an empty src/ and return the app path."""
    (tmp_path / "src").mkdir(parents=True)
    return tmp_path


def _write(tmp_path: Path, *files: str) -> Path:
    """Lay out marker files under <app>/src and return the app path."""
    app_path = _app(tmp_path)
    for f in files:
        (app_path / "src" / f).write_text("x")
    return app_path


# A representative auto-detecting toolchain per language and the marker file
# that should make ONLY that toolchain accept. Generic/Static are excluded:
# they don't auto-detect on a language marker file.
_MARKERS: dict[type[LanguageToolchain], str] = {
    PythonToolchain: "requirements.txt",
    NodeToolchain: "package.json",
    RustToolchain: "Cargo.toml",
    RubyToolchain: "Gemfile",
    GoToolchain: "go.mod",
    JavaToolchain: "pom.xml",
    PHPToolchain: "composer.json",
    ElixirToolchain: "mix.exs",
    DotNetToolchain: "app.csproj",
    ClojureToolchain: "deps.edn",
}


class TestLanguageDisambiguation:
    """
    A marker file for one language must not trip another's accept().

    This is the core safety property: misrouting an app to the wrong toolchain
    is a deploy failure. We assert the full cross-product, so adding a new
    over-eager detection (e.g. PHP grabbing every dir) fails loudly here.
    """

    def test_each_marker_accepted_only_by_its_own_toolchain(self, tmp_path):
        for owner, marker in _MARKERS.items():
            app_path = _write(tmp_path / owner.__name__, marker)
            for tc_cls in _MARKERS:
                tc = tc_cls("app", app_path)
                accepted = tc.accept()
                if tc_cls is owner:
                    assert accepted, f"{tc_cls.__name__} rejected its own {marker}"
                else:
                    assert not accepted, (
                        f"{tc_cls.__name__} wrongly accepted {owner.__name__}'s {marker}"
                    )

    def test_empty_project_accepted_by_none(self, tmp_path):
        """An app dir with no marker files matches no auto-detecting toolchain."""
        app_path = _app(tmp_path)
        for tc_cls in _MARKERS:
            assert not tc_cls("app", app_path).accept()


class TestPythonDetection:
    """Python accepts on requirements.txt OR pyproject.toml (ADR 039 inputs)."""

    def test_accepts_requirements_txt(self, tmp_path):
        assert PythonToolchain("app", _write(tmp_path, "requirements.txt")).accept()

    def test_accepts_pyproject_toml(self, tmp_path):
        assert PythonToolchain("app", _write(tmp_path, "pyproject.toml")).accept()

    def test_rejects_without_python_markers(self, tmp_path):
        assert not PythonToolchain("app", _write(tmp_path, "main.py")).accept()


class TestGoDetection:
    """Go accepts on go.mod, legacy Godeps, or any raw *.go file."""

    def test_accepts_go_mod(self, tmp_path):
        assert GoToolchain("app", _write(tmp_path, "go.mod")).accept()

    def test_accepts_raw_go_file(self, tmp_path):
        assert GoToolchain("app", _write(tmp_path, "server.go")).accept()

    def test_accepts_legacy_godeps(self, tmp_path):
        app_path = _app(tmp_path)
        (app_path / "src" / "Godeps").mkdir()
        assert GoToolchain("app", app_path).accept()

    def test_rejects_without_go_markers(self, tmp_path):
        assert not GoToolchain("app", _write(tmp_path, "README.md")).accept()


class TestJavaDetection:
    """Java accepts on Maven (pom.xml) or Gradle (build.gradle[.kts])."""

    def test_accepts_maven(self, tmp_path):
        tc = JavaToolchain("app", _write(tmp_path, "pom.xml"))
        assert tc.accept()
        assert tc.is_maven
        assert not tc.is_gradle

    def test_accepts_gradle_groovy(self, tmp_path):
        tc = JavaToolchain("app", _write(tmp_path, "build.gradle"))
        assert tc.accept()
        assert tc.is_gradle
        assert not tc.is_maven

    def test_accepts_gradle_kotlin_dsl(self, tmp_path):
        tc = JavaToolchain("app", _write(tmp_path, "build.gradle.kts"))
        assert tc.accept()
        assert tc.is_gradle

    def test_rejects_without_build_file(self, tmp_path):
        assert not JavaToolchain("app", _write(tmp_path, "Main.java")).accept()


class TestPhpDetection:
    """PHP accepts on composer.json, index.php, or any *.php in root."""

    def test_accepts_composer(self, tmp_path):
        tc = PHPToolchain("app", _write(tmp_path, "composer.json"))
        assert tc.accept()
        assert tc._has_composer()

    def test_accepts_index_php(self, tmp_path):
        tc = PHPToolchain("app", _write(tmp_path, "index.php"))
        assert tc.accept()
        assert not tc._has_composer()

    def test_accepts_arbitrary_php_file(self, tmp_path):
        assert PHPToolchain("app", _write(tmp_path, "app.php")).accept()

    def test_rejects_without_php(self, tmp_path):
        assert not PHPToolchain("app", _write(tmp_path, "index.html")).accept()


class TestDotNetDetection:
    """`.NET` accepts on any *.csproj / *.fsproj / *.sln (glob, not fixed name)."""

    def test_accepts_csproj(self, tmp_path):
        assert DotNetToolchain("app", _write(tmp_path, "Web.csproj")).accept()

    def test_accepts_fsproj(self, tmp_path):
        assert DotNetToolchain("app", _write(tmp_path, "Web.fsproj")).accept()

    def test_accepts_sln(self, tmp_path):
        assert DotNetToolchain("app", _write(tmp_path, "Solution.sln")).accept()

    def test_rejects_without_dotnet_project(self, tmp_path):
        assert not DotNetToolchain("app", _write(tmp_path, "Program.cs")).accept()


class TestClojureDetection:
    """Clojure accepts Leiningen (project.clj) and CLI (deps.edn) layouts."""

    def test_accepts_leiningen(self, tmp_path):
        tc = ClojureToolchain("app", _write(tmp_path, "project.clj"))
        assert tc.accept()
        assert tc.is_leiningen_app
        assert not tc.is_cli_app

    def test_accepts_cli_deps_edn(self, tmp_path):
        tc = ClojureToolchain("app", _write(tmp_path, "deps.edn"))
        assert tc.accept()
        assert tc.is_cli_app
        assert not tc.is_leiningen_app

    def test_rejects_without_clojure_markers(self, tmp_path):
        assert not ClojureToolchain("app", _write(tmp_path, "core.clj")).accept()


class TestRubyAndElixirDetection:
    def test_ruby_accepts_gemfile(self, tmp_path):
        assert RubyToolchain("app", _write(tmp_path, "Gemfile")).accept()

    def test_ruby_rejects_without_gemfile(self, tmp_path):
        assert not RubyToolchain("app", _write(tmp_path, "app.rb")).accept()

    def test_elixir_accepts_mix_exs(self, tmp_path):
        assert ElixirToolchain("app", _write(tmp_path, "mix.exs")).accept()

    def test_elixir_rejects_without_mix(self, tmp_path):
        assert not ElixirToolchain("app", _write(tmp_path, "main.ex")).accept()


class TestGenericToolchainDetection:
    """
    Generic NEVER auto-detects; it accepts only on explicit opt-in.

    Auto-accepting would shadow every real language toolchain, so this guards
    the "must be explicitly requested" contract from generic.py.
    """

    def _ctx(self, tmp_path, build_section):
        src = tmp_path / "src"
        src.mkdir()
        return BuildContext(
            app_name="app",
            source_path=src,
            app_config={"hop3_config": {"build": build_section}},
        )

    def test_accepts_when_toolchain_generic(self, tmp_path):
        ctx = self._ctx(tmp_path, {"toolchain": "generic"})
        assert GenericToolchain(ctx).accept()

    def test_accepts_when_toolchain_none(self, tmp_path):
        ctx = self._ctx(tmp_path, {"toolchain": "none"})
        assert GenericToolchain(ctx).accept()

    def test_rejects_when_no_toolchain_declared(self, tmp_path):
        ctx = self._ctx(tmp_path, {})
        assert not GenericToolchain(ctx).accept()

    def test_rejects_in_legacy_mode_without_context(self, tmp_path):
        # No BuildContext => no hop3.toml => cannot opt in => must reject.
        app_path = _app(tmp_path)
        assert not GenericToolchain("app", app_path).accept()
