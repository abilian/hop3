# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pure build-decision helpers shared by every toolchain (LanguageToolchain base).

These cover the functional core of the build path that does NOT touch a real
toolchain binary:

- ``_get_workers``: Procfile parsing, including the ``src/hop3/Procfile``
  alternate location and the no-Procfile case.
- ``_get_custom_build_command``: how ``[build].build`` from hop3.toml is read
  (string, list-joined-with-&&, or absent).
- ``_make_build_artifact`` / ``_make_runtime_config``: the artifact shape every
  deployer reads back (kind, builder, app_name, location, workers, metadata).
- ``check_exists``: the str/list overload used by most ``accept()`` methods.

We use StaticToolchain as a concrete stand-in for the abstract base (it adds no
behaviour to these inherited helpers).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.protocols import BuildContext
from hop3.toolchains.static import StaticToolchain

if TYPE_CHECKING:
    from pathlib import Path


def _toolchain(tmp_path: Path) -> StaticToolchain:
    """Legacy-mode toolchain with sources at <app>/src."""
    (tmp_path / "src").mkdir()
    return StaticToolchain("myapp", tmp_path)


class TestGetWorkers:
    """Procfile -> worker dict, matching AppConfig.get_file() lookup order."""

    def test_parses_standard_procfile(self, tmp_path):
        tc = _toolchain(tmp_path)
        (tc.src_path / "Procfile").write_text("web: gunicorn app:app\nworker: celery\n")

        workers = tc._get_workers()

        assert workers == {"web": "gunicorn app:app", "worker": "celery"}

    def test_prefers_hop3_subdir_procfile(self, tmp_path):
        """A Procfile under src/hop3/ takes precedence over src/Procfile."""
        tc = _toolchain(tmp_path)
        (tc.src_path / "Procfile").write_text("web: from-root\n")
        (tc.src_path / "hop3").mkdir()
        (tc.src_path / "hop3" / "Procfile").write_text("web: from-hop3-dir\n")

        workers = tc._get_workers()

        assert workers == {"web": "from-hop3-dir"}

    def test_no_procfile_returns_empty(self, tmp_path):
        tc = _toolchain(tmp_path)
        assert tc._get_workers() == {}


class TestCustomBuildCommand:
    """`[build].build` extraction from hop3.toml app_config."""

    def _ctx_toolchain(self, tmp_path, build_section):
        src = tmp_path / "src"
        src.mkdir()
        ctx = BuildContext(
            app_name="myapp",
            source_path=src,
            app_config={"hop3_config": {"build": build_section}},
        )
        return StaticToolchain(ctx)

    def test_string_command_returned_as_is(self, tmp_path):
        tc = self._ctx_toolchain(tmp_path, {"build": "make all"})
        assert tc._get_custom_build_command() == "make all"

    def test_list_command_joined_with_and(self, tmp_path):
        """A list of commands is joined with ' && ' so it runs as one shell line."""
        tc = self._ctx_toolchain(tmp_path, {"build": ["npm ci", "npm run build"]})
        assert tc._get_custom_build_command() == "npm ci && npm run build"

    def test_empty_list_returns_none(self, tmp_path):
        tc = self._ctx_toolchain(tmp_path, {"build": []})
        assert tc._get_custom_build_command() is None

    def test_missing_build_key_returns_none(self, tmp_path):
        tc = self._ctx_toolchain(tmp_path, {})
        assert tc._get_custom_build_command() is None

    def test_legacy_mode_without_context_returns_none(self, tmp_path):
        tc = _toolchain(tmp_path)  # no BuildContext
        assert tc._get_custom_build_command() is None


class TestBuildArtifactShape:
    """The artifact every deployer reads back must carry the inputs faithfully."""

    def test_make_runtime_config_includes_procfile_workers(self, tmp_path):
        tc = _toolchain(tmp_path)
        (tc.src_path / "Procfile").write_text("web: serve\n")

        runtime = tc._make_runtime_config(
            env_vars={"FOO": "bar"}, path_prepend=["/opt/bin"]
        )

        assert runtime.workers == {"web": "serve"}
        assert runtime.env_vars == {"FOO": "bar"}
        assert runtime.path_prepend == ["/opt/bin"]
        assert runtime.working_dir == str(tc.src_path)

    def test_make_build_artifact_carries_kind_name_location_metadata(self, tmp_path):
        tc = _toolchain(tmp_path)

        artifact = tc._make_build_artifact(kind="python", metadata={"k": "v"})

        assert artifact.kind == "python"
        assert artifact.builder == "local"
        assert artifact.app_name == "myapp"
        assert artifact.location == str(tc.src_path)
        assert artifact.metadata == {"k": "v"}
        # built_at / build_id are populated (timestamp + git/uuid id).
        assert artifact.built_at
        assert artifact.build_id

    def test_make_build_artifact_defaults_empty_metadata(self, tmp_path):
        tc = _toolchain(tmp_path)
        artifact = tc._make_build_artifact(kind="static")
        assert artifact.metadata == {}


class TestCheckExists:
    """check_exists underpins most accept() methods: str or list-of-str, in src/."""

    def test_single_filename_present(self, tmp_path):
        tc = _toolchain(tmp_path)
        (tc.src_path / "go.mod").write_text("module x")
        assert tc.check_exists("go.mod")

    def test_single_filename_absent(self, tmp_path):
        tc = _toolchain(tmp_path)
        assert not tc.check_exists("go.mod")

    def test_list_matches_if_any_present(self, tmp_path):
        tc = _toolchain(tmp_path)
        (tc.src_path / "pyproject.toml").write_text("[project]")
        assert tc.check_exists(["requirements.txt", "pyproject.toml"])

    def test_list_false_when_none_present(self, tmp_path):
        tc = _toolchain(tmp_path)
        assert not tc.check_exists(["requirements.txt", "pyproject.toml"])
