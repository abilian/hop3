# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The ``build()`` orchestration of each language toolchain, driven end-to-end.

The base-helper tests (``test_toolchain_build_helpers``) cover the shared plumbing;
these cover what each toolchain's ``build()`` actually *does* — the exact commands
it issues and the ``BuildArtifact`` it returns — without a real toolchain binary.

The shell is the seam: we replace ``tc.shell`` with a recorder, so every command
is captured instead of run. That lets us pin the reproducibility-critical choices
(``npm ci`` not ``npm install``, ``bundle install --frozen``, ``--require-hashes``
when a requirements file is fully hashed) and the artifact shape every deployer
reads back.

Legacy construction is ``Toolchain("name", app_path)`` (sources at ``app_path/src``);
the custom-build and pin paths need a ``BuildContext`` to carry ``hop3.toml`` config.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hop3.core.env import Env
from hop3.core.protocols import BuildContext
from hop3.toolchains import (
    ClojureToolchain,
    DotNetToolchain,
    GenericToolchain,
    GoToolchain,
    JavaToolchain,
    NodeToolchain,
    PHPToolchain,
    PythonToolchain,
    RubyToolchain,
    RustToolchain,
    node as node_mod,
    python as py_mod,
    rust as rust_mod,
)


class ShellRecorder:
    """Stands in for ``tc.shell``: records commands, returns a chosen returncode."""

    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.calls: list[str] = []
        self.returncode = returncode
        self.stdout = stdout

    def __call__(self, command, cwd="", *, env=None, check=True):
        self.calls.append(command)
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, "")


def _src(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    """Create ``<tmp>/src`` (the legacy source dir) with the given files."""
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for name, content in (files or {}).items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return src


def _record(tc, monkeypatch, returncode=0, stdout="") -> ShellRecorder:
    """Swap ``tc.shell`` for a recorder and return it."""
    recorder = ShellRecorder(returncode=returncode, stdout=stdout)
    monkeypatch.setattr(tc, "shell", recorder)
    return recorder


def _ctx_toolchain(cls, tmp_path: Path, build_section: dict, files=None):
    """A toolchain built from a BuildContext carrying ``[build]`` config."""
    src = _src(tmp_path, files)
    ctx = BuildContext(
        app_name="myapp",
        source_path=src,
        app_config={"hop3_config": {"build": build_section}},
    )
    return cls(ctx)


class TestRubyBuild:
    def test_installs_frozen_gems_and_shapes_artifact(self, tmp_path, monkeypatch):
        _src(tmp_path, {"Gemfile": "source 'https://rubygems.org'\n"})
        tc = RubyToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)

        artifact = tc.build()

        # --frozen refuses to re-resolve a stale lockfile (reproducibility).
        assert "bundle install --frozen" in rec.calls
        assert any("bundle config set path" in c for c in rec.calls)
        assert artifact.kind == "ruby"
        env_vars = artifact.runtime.env_vars
        assert env_vars["GEM_HOME"] == str(tc.virtual_env)
        assert env_vars["BUNDLE_PATH"] == str(tc.virtual_env)
        assert str(tc.virtual_env / "bin") in artifact.runtime.path_prepend

    def test_make_virtual_env_is_idempotent(self, tmp_path, monkeypatch):
        _src(tmp_path)
        tc = RubyToolchain("myapp", tmp_path)
        tc.virtual_env.mkdir(parents=True)  # already exists -> skip creation branch
        rec = _record(tc, monkeypatch)
        tc.make_virtual_env(tc.get_env())
        assert (tc.virtual_env / ".bundle" / "cache").is_dir()
        assert any("bundle config set path" in c for c in rec.calls)


class TestGoBuild:
    def test_custom_build_command_short_circuits(self, tmp_path, monkeypatch):
        tc = _ctx_toolchain(GoToolchain, tmp_path, {"build": "make server"})
        rec = _record(tc, monkeypatch)

        artifact = tc.build()

        assert rec.calls == ["make server"]
        assert artifact.kind == "go"
        assert artifact.metadata == {"custom_build": True}

    def test_default_downloads_tidies_and_compiles(self, tmp_path, monkeypatch):
        _src(tmp_path, {"go.mod": "module x\n", "main.go": "package main\n"})
        tc = GoToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)

        artifact = tc.build()

        assert "go mod download" in rec.calls
        assert "go mod tidy" in rec.calls
        assert "go build -o myapp ." in rec.calls
        assert artifact.kind == "go"

    def test_compile_failure_is_tolerated_for_go_run_apps(self, tmp_path, monkeypatch):
        # A non-zero `go build` must not abort: the Procfile may use `go run`.
        _src(tmp_path, {"main.go": "package main\n"})
        tc = GoToolchain("myapp", tmp_path)
        _record(tc, monkeypatch, returncode=1)
        assert tc.build().kind == "go"  # must not raise


class TestRustBuild:
    def test_default_release_build(self, tmp_path, monkeypatch):
        _src(tmp_path, {"Cargo.toml": "[package]\n"})
        tc = RustToolchain("myapp", tmp_path)
        monkeypatch.setattr(rust_mod, "find_cargo", lambda: "cargo")
        rec = _record(tc, monkeypatch)

        artifact = tc.build()

        assert "cargo build --release" in rec.calls
        assert artifact.kind == "rust"

    def test_custom_build_overrides_default(self, tmp_path, monkeypatch):
        tc = _ctx_toolchain(
            RustToolchain, tmp_path, {"build": "cargo build --features foo"}
        )
        monkeypatch.setattr(rust_mod, "find_cargo", lambda: "cargo")
        rec = _record(tc, monkeypatch)
        tc.build()
        assert rec.calls == ["cargo build --features foo"]

    def test_compile_failure_raises_loudly(self, tmp_path, monkeypatch):
        # A failed cargo build must abort, not leave a missing binary for runtime.
        _src(tmp_path, {"Cargo.toml": "[package]\n"})
        tc = RustToolchain("myapp", tmp_path)
        monkeypatch.setattr(rust_mod, "find_cargo", lambda: "cargo")
        _record(tc, monkeypatch, returncode=1)
        with pytest.raises(RuntimeError, match="Rust compilation failed"):
            tc.build()


class TestFindCargo:
    def test_prefers_a_known_rustup_path(self, tmp_path, monkeypatch):
        cargo = tmp_path / "cargo"
        cargo.write_text("#!/bin/sh\n")
        monkeypatch.setattr(rust_mod, "CARGO_PATHS", [cargo])
        assert rust_mod.find_cargo() == str(cargo)

    def test_falls_back_to_path_lookup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rust_mod, "CARGO_PATHS", [tmp_path / "missing"])
        monkeypatch.setattr(rust_mod.shutil, "which", lambda _b: "/opt/bin/cargo")
        assert rust_mod.find_cargo() == "/opt/bin/cargo"

    def test_last_resort_is_bare_cargo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rust_mod, "CARGO_PATHS", [tmp_path / "missing"])
        monkeypatch.setattr(rust_mod.shutil, "which", lambda _b: None)
        assert rust_mod.find_cargo() == "cargo"


class TestClojureBuild:
    def test_leiningen_app(self, tmp_path, monkeypatch):
        _src(tmp_path, {"project.clj": "(defproject x)\n"})
        tc = ClojureToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)

        artifact = tc.build()

        assert "lein clean" in rec.calls
        assert "lein uberjar" in rec.calls
        assert artifact.metadata == {"is_leiningen": True}
        assert "LEIN_HOME" in artifact.runtime.env_vars

    def test_cli_deps_app(self, tmp_path, monkeypatch):
        _src(tmp_path, {"deps.edn": "{}\n"})
        tc = ClojureToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)

        artifact = tc.build()

        assert "clojure -T:build release" in rec.calls
        assert artifact.metadata == {"is_leiningen": False}
        assert "CLJ_CONFIG" in artifact.runtime.env_vars


class TestJavaBuild:
    def test_maven(self, tmp_path, monkeypatch):
        _src(tmp_path, {"pom.xml": "<project/>\n"})
        tc = JavaToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)
        assert tc.build().kind == "java"
        assert "mvn -B package -DskipTests" in rec.calls

    def test_gradle_wrapper_preferred(self, tmp_path, monkeypatch):
        _src(tmp_path, {"build.gradle": "\n", "gradlew": "#!/bin/sh\n"})
        tc = JavaToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)
        tc.build()
        assert "./gradlew build -x test" in rec.calls

    def test_gradle_without_wrapper(self, tmp_path, monkeypatch):
        _src(tmp_path, {"build.gradle": "\n"})
        tc = JavaToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)
        tc.build()
        assert "gradle build -x test" in rec.calls

    def test_no_build_tool_still_returns_artifact(self, tmp_path, monkeypatch):
        _src(tmp_path)  # neither pom nor gradle
        tc = JavaToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)
        assert tc.build().kind == "java"
        assert rec.calls == []


class TestDotNetBuild:
    def test_restores_then_builds_release(self, tmp_path, monkeypatch):
        _src(tmp_path, {"app.csproj": "<Project/>\n"})
        tc = DotNetToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)
        assert tc.build().kind == "dotnet"
        assert rec.calls == ["dotnet restore", "dotnet build -c Release"]

    def test_build_failure_is_logged_not_raised(self, tmp_path, monkeypatch):
        _src(tmp_path, {"app.csproj": "<Project/>\n"})
        tc = DotNetToolchain("myapp", tmp_path)
        _record(tc, monkeypatch, returncode=1)
        assert tc.build().kind == "dotnet"  # must not raise


class TestGenericBuild:
    def test_runs_custom_build_command(self, tmp_path, monkeypatch):
        tc = _ctx_toolchain(GenericToolchain, tmp_path, {"build": "make release"})
        rec = _record(tc, monkeypatch)
        artifact = tc.build()
        assert rec.calls == ["make release"]
        assert artifact.metadata == {"toolchain": "generic"}

    def test_no_command_assumes_prebuilt(self, tmp_path, monkeypatch):
        _src(tmp_path)
        tc = GenericToolchain("myapp", tmp_path)  # legacy: no context, no custom build
        rec = _record(tc, monkeypatch)
        assert tc.build().kind == "generic"
        assert rec.calls == []


class TestNodeBuild:
    def test_end_to_end_uses_npm_ci_from_lockfile(self, tmp_path, monkeypatch):
        _src(tmp_path, {"package.json": "{}", "package-lock.json": "{}"})
        tc = NodeToolchain("myapp", tmp_path)
        monkeypatch.setattr(node_mod, "check_binaries", lambda _b: True)
        rec = _record(tc, monkeypatch)

        artifact = tc.build()

        assert any(c.startswith("npm ci") for c in rec.calls)
        assert artifact.kind == "node"
        assert artifact.runtime.env_vars["NODE_PATH"].endswith("node_modules")
        assert artifact.metadata["node_modules"].endswith("node_modules")

    def test_declared_node_version_flows_from_toml(self, tmp_path):
        tc = _ctx_toolchain(NodeToolchain, tmp_path, {"node-version": "20.11.0"})
        assert tc._get_declared_node_version() == "20.11.0"

    def test_declared_node_version_absent_without_context(self, tmp_path):
        _src(tmp_path)
        tc = NodeToolchain("myapp", tmp_path)
        assert tc._get_declared_node_version() is None


class TestPHPBuild:
    def test_composer_install_default(self, tmp_path, monkeypatch):
        _src(tmp_path, {"composer.json": "{}"})
        tc = PHPToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)
        assert tc.build().kind == "php"
        assert any("composer install" in c for c in rec.calls)

    def test_custom_build_overrides_composer(self, tmp_path, monkeypatch):
        tc = _ctx_toolchain(
            PHPToolchain, tmp_path, {"build": "make php"}, files={"composer.json": "{}"}
        )
        rec = _record(tc, monkeypatch)
        tc.build()
        assert rec.calls == ["make php"]

    def test_no_composer_assumes_vendored(self, tmp_path, monkeypatch):
        _src(tmp_path)  # no composer.json
        tc = PHPToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)
        assert tc.build().kind == "php"
        assert rec.calls == []  # nothing to install


def _fake_venv(tmp_path: Path) -> Path:
    """A minimal venv layout so install_virtualenv's existence asserts pass."""
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    return python


class TestPythonInstallVirtualenv:
    """The reproducibility gate: how requirements/pyproject/uv drive the install."""

    def _tc(self, tmp_path, files):
        _src(tmp_path, files)
        _fake_venv(tmp_path)
        return PythonToolchain("myapp", tmp_path)

    def test_pinned_requirements_install_without_require_hashes(
        self, tmp_path, monkeypatch
    ):
        tc = self._tc(tmp_path, {"requirements.txt": "flask==3.0.0\n"})
        rec = _record(tc, monkeypatch)
        tc.install_virtualenv()
        install = next(c for c in rec.calls if "-r" in c)
        assert "requirements.txt" in install
        assert "--require-hashes" not in install

    def test_fully_hashed_requirements_enable_require_hashes(
        self, tmp_path, monkeypatch
    ):
        reqs = "flask==3.0.0 --hash=sha256:abc\n"
        tc = self._tc(tmp_path, {"requirements.txt": reqs})
        rec = _record(tc, monkeypatch)
        tc.install_virtualenv()
        assert any("--require-hashes" in c for c in rec.calls)

    def test_unpinned_requirements_abort(self, tmp_path, monkeypatch):
        tc = self._tc(tmp_path, {"requirements.txt": "flask\n"})
        _record(tc, monkeypatch)
        with pytest.raises(RuntimeError, match="unpinned"):
            tc.install_virtualenv()

    def test_pyproject_only_installs_the_project(self, tmp_path, monkeypatch):
        tc = self._tc(tmp_path, {"pyproject.toml": "[project]\nname='x'\n"})
        rec = _record(tc, monkeypatch)
        tc.install_virtualenv()
        assert any(c.endswith("pip install .") for c in rec.calls)

    def test_both_files_present_is_an_error(self, tmp_path, monkeypatch):
        tc = self._tc(
            tmp_path, {"requirements.txt": "flask==3.0.0\n", "pyproject.toml": "[x]\n"}
        )
        _record(tc, monkeypatch)
        with pytest.raises(RuntimeError, match="Declare one"):
            tc.install_virtualenv()

    def test_uv_lock_takes_the_uv_path(self, tmp_path, monkeypatch):
        tc = self._tc(tmp_path, {"pyproject.toml": "[project]\n", "uv.lock": "\n"})
        _record(tc, monkeypatch)
        monkeypatch.setattr(tc, "_ensure_uv_installed", lambda: True)
        called = []
        monkeypatch.setattr(tc, "_install_with_uv", lambda: called.append(True))
        tc.install_virtualenv()
        assert called == [True]


class TestPythonBuildAndHelpers:
    def test_build_shapes_artifact_with_pythonpath_for_src_layout(
        self, tmp_path, monkeypatch
    ):
        _src(tmp_path, {"requirements.txt": "flask==3.0.0\n"})
        (tmp_path / "src" / "src").mkdir()  # src-layout project
        (tmp_path / "venv" / "bin").mkdir(parents=True)
        tc = PythonToolchain("myapp", tmp_path)
        # Isolate build()'s artifact-shaping from the real venv machinery.
        monkeypatch.setattr(tc, "make_virtual_env", lambda: None)
        monkeypatch.setattr(tc, "install_virtualenv", lambda: None)

        artifact = tc.build()

        assert artifact.kind == "python"
        env_vars = artifact.runtime.env_vars
        assert env_vars["PYTHONUNBUFFERED"] == "1"
        assert env_vars["PYTHONPATH"] == str(tmp_path / "src" / "src")
        assert artifact.metadata["python_path"].endswith("venv/bin/python")

    def test_find_uv_binary_prefers_path_then_candidates(self, tmp_path, monkeypatch):
        _src(tmp_path)
        tc = PythonToolchain("myapp", tmp_path)
        monkeypatch.setattr(py_mod.shutil, "which", lambda _b: "/usr/bin/uv")
        assert tc._find_uv_binary() == "/usr/bin/uv"
        monkeypatch.setattr(py_mod.shutil, "which", lambda _b: None)
        assert tc._find_uv_binary() == "uv"  # falls through to the bare name

    def test_get_env_sets_python_flags(self, tmp_path):
        _src(tmp_path)
        env = PythonToolchain("myapp", tmp_path).get_env()
        assert env["PYTHONUNBUFFERED"] == "1"
        assert env["PYTHONIOENCODING"] == "UTF_8:replace"

    def test_has_uv_reflects_which(self, tmp_path, monkeypatch):
        _src(tmp_path)
        tc = PythonToolchain("myapp", tmp_path)
        monkeypatch.setattr(py_mod.shutil, "which", lambda _b: "/usr/bin/uv")
        assert tc._has_uv() is True
        monkeypatch.setattr(py_mod.shutil, "which", lambda _b: None)
        assert tc._has_uv() is False

    def test_is_python_executable(self, tmp_path):
        _src(tmp_path)
        tc = PythonToolchain("myapp", tmp_path)
        assert tc._is_python_executable(Path(sys.executable)) is True
        assert tc._is_python_executable(tmp_path / "nope") is False

    def test_find_best_python_returns_a_working_interpreter(self):
        # Runs for real: on any dev/CI box at least /usr/bin/python3 exists.
        assert py_mod._find_best_python().startswith("/usr/bin/python")

    def test_missing_both_files_raises_file_not_found(self, tmp_path, monkeypatch):
        _src(tmp_path)  # neither requirements.txt nor pyproject.toml
        _fake_venv(tmp_path)
        tc = PythonToolchain("myapp", tmp_path)
        _record(tc, monkeypatch)
        with pytest.raises(FileNotFoundError):
            tc.install_virtualenv()

    def test_uv_lock_falls_back_to_pip_when_uv_unavailable(self, tmp_path, monkeypatch):
        _src(tmp_path, {"requirements.txt": "flask==3.0.0\n", "uv.lock": "\n"})
        _fake_venv(tmp_path)
        tc = PythonToolchain("myapp", tmp_path)
        rec = _record(tc, monkeypatch)
        monkeypatch.setattr(tc, "_ensure_uv_installed", lambda: False)
        tc.install_virtualenv()
        # uv couldn't be installed, so the pip path drives the install instead.
        assert any("-r" in c and "requirements.txt" in c for c in rec.calls)


class TestNodeInstallSteps:
    def test_install_modules_runs_custom_build(self, tmp_path, monkeypatch):
        tc = _ctx_toolchain(
            NodeToolchain,
            tmp_path,
            {"build": "pnpm install"},
            files={"package.json": "{}"},
        )
        rec = _record(tc, monkeypatch)
        tc.install_modules(Env({}))
        assert rec.calls == ["pnpm install"]

    def test_install_node_provisions_pinned_version(self, tmp_path, monkeypatch):
        _src(tmp_path)
        tc = NodeToolchain("myapp", tmp_path)
        monkeypatch.setattr(node_mod, "check_binaries", lambda _b: True)
        rec = _record(tc, monkeypatch)
        tc.install_node(Env({"NODE_VERSION": "22.13.1"}))
        assert any("nodeenv --prebuilt --node=22.13.1" in c for c in rec.calls)


class TestBaseHelpers:
    def _tc(self, tmp_path):
        _src(tmp_path)
        return PythonToolchain("myapp", tmp_path)

    def test_shell_merges_env_over_os_environ(self, tmp_path):
        # A real (cheap) command: exercises the env-merge branch of base.shell.
        tc = self._tc(tmp_path)
        result = tc.shell("true", env={"FOO": "bar"})
        assert result.returncode == 0

    def test_get_home_dir_prefers_env(self, tmp_path, monkeypatch):
        tc = self._tc(tmp_path)
        monkeypatch.setenv("HOME", "/home/someone")
        assert tc._get_home_dir() == "/home/someone"

    def test_get_home_dir_falls_back_to_passwd(self, tmp_path, monkeypatch):
        tc = self._tc(tmp_path)
        monkeypatch.delenv("HOME", raising=False)
        # No HOME in env -> resolved from the passwd database (a real absolute path).
        assert tc._get_home_dir().startswith("/")

    def test_get_build_id_from_git_head(self, tmp_path):
        src = _src(tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=src, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=src, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=src, check=True)
        (src / "f").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=src, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "init"],
            cwd=src,
            check=True,
            env={"GIT_CONFIG_GLOBAL": "/dev/null", "PATH": os.environ["PATH"]},
        )
        build_id = PythonToolchain("myapp", tmp_path)._get_build_id()
        assert len(build_id) == 12
