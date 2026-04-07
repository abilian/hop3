# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for individual template output correctness.

Goes beyond smoke tests to verify structural properties of the generated
Nix expressions: correct heredoc termination, placeholder presence,
sed commands, and Nix syntax structure.
"""

from __future__ import annotations

import pytest

from hop3.plugins.build.nix.gen.registry import generate
from hop3.plugins.build.nix.gen.spec import AppSpec, FileMapping, Source

# --- prebuilt-binary ---


def test_prebuilt_binary_requires_binary_name():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="prebuilt-binary",
        source=Source(url="x", sha256="x", executable=True),
    )
    with pytest.raises(ValueError, match="binary_name"):
        generate(spec)


def test_prebuilt_binary_sed_replaces_bindir():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="prebuilt-binary",
        binary_name="test",
        source=Source(url="x", sha256="x", executable=True),
    )
    output = generate(spec)
    assert 'sed -i "s|BINDIR|$out/bin|g"' in output


def test_prebuilt_binary_wrapper_heredoc_terminated():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="prebuilt-binary",
        binary_name="test",
        source=Source(url="x", sha256="x", executable=True),
    )
    output = generate(spec)
    assert "WRAPPER" in output
    # Should have both opening and closing
    wrapper_count = output.count("WRAPPER")
    assert wrapper_count == 2, f"Expected 2 WRAPPER markers, got {wrapper_count}"


def test_prebuilt_binary_exec_args():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="prebuilt-binary",
        binary_name="mybin",
        exec_args=["serve", "--flag"],
        source=Source(url="x", sha256="x", executable=True),
    )
    output = generate(spec)
    assert "exec BINDIR/mybin serve --flag" in output


# --- prebuilt-archive ---


def test_prebuilt_archive_requires_exec_target():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="prebuilt-archive",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        file_mappings=[FileMapping(source="bin/x", destination="bin/")],
    )
    with pytest.raises(ValueError, match="exec_target"):
        generate(spec)


def test_prebuilt_archive_requires_file_mappings():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="prebuilt-archive",
        exec_target="mybin",
        source=Source(url="x", sha256="x", archive="tar-gz"),
    )
    with pytest.raises(ValueError, match="file_mappings"):
        generate(spec)


def test_prebuilt_archive_zip_has_unzip():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="prebuilt-archive",
        exec_target="mybin",
        source=Source(url="x", sha256="x", archive="zip"),
        source_root=".",
        file_mappings=[FileMapping(source="bin/x", destination="bin/")],
    )
    output = generate(spec)
    assert "pkgs.unzip" in output
    assert "unzip $src" in output


def test_prebuilt_archive_sed_replaces_sharedir():
    spec = AppSpec(
        pname="myapp",
        version="1.0",
        description="t",
        template="prebuilt-archive",
        exec_target="mybin",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        source_root="myapp",
        file_mappings=[FileMapping(source="bin/x", destination="bin/")],
    )
    output = generate(spec)
    assert 'sed -i "s|SHAREDIR|$out/share/myapp|g"' in output


# --- php-app ---


def test_php_app_single_file():
    spec = AppSpec(
        pname="adminer",
        version="4.8.1",
        description="t",
        template="php-app",
        php_extensions=["mysqli"],
        single_file=True,
        source=Source(url="x", sha256="x"),
        extra_paths=["${php}/bin"],
    )
    output = generate(spec)
    assert "dontUnpack = true" in output
    assert "cp $src $out/app/index.php" in output


def test_php_app_composer():
    spec = AppSpec(
        pname="bookstack",
        version="1.0",
        description="t",
        template="php-app",
        php_extensions=["mysqli"],
        needs_composer=True,
        source=Source(url="x", sha256="x", archive="tar-gz"),
        extra_paths=["${php}/bin"],
    )
    output = generate(spec)
    assert "__noChroot = true" in output
    assert "composer install" in output
    assert "nativeBuildInputs = [ php composer" in output


def test_php_app_artisan_serve():
    spec = AppSpec(
        pname="laravel-app",
        version="1.0",
        description="t",
        template="php-app",
        php_extensions=[],
        serve_mode="artisan",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        extra_paths=["${php}/bin"],
    )
    output = generate(spec)
    assert "artisan serve" in output
    assert "--host=0.0.0.0" in output


def test_php_app_web_root():
    spec = AppSpec(
        pname="dolibarr",
        version="1.0",
        description="t",
        template="php-app",
        php_extensions=[],
        web_root="htdocs",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        extra_paths=["${php}/bin"],
    )
    output = generate(spec)
    assert "APPDIR/htdocs" in output


def test_php_app_sed_replaces_phpbin():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="php-app",
        php_extensions=[],
        source=Source(url="x", sha256="x", archive="tar-gz"),
        extra_paths=["${php}/bin"],
    )
    output = generate(spec)
    assert "sed -i" in output
    assert "PHPBIN" in output
    assert "APPDIR" in output


def test_php_app_source_root():
    """zip-with-wrapper-dir pattern (limesurvey)."""
    spec = AppSpec(
        pname="limesurvey",
        version="1.0",
        description="t",
        template="php-app",
        php_extensions=[],
        source=Source(url="x", sha256="x", archive="zip"),
        source_root="limesurvey",
        extra_paths=["${php}/bin"],
    )
    output = generate(spec)
    assert "cp -r limesurvey/. $out/app/" in output


# --- java-war ---


def test_java_war_requires_war_file():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="java-war",
        source=Source(url="x", sha256="x"),
    )
    with pytest.raises(ValueError, match="war_file"):
        generate(spec)


def test_java_war_sed_replaces_javabin_and_warpath():
    spec = AppSpec(
        pname="jenkins",
        version="1.0",
        description="t",
        template="java-war",
        war_file="jenkins.war",
        runtime_package="jdk17",
        source=Source(url="x", sha256="x"),
        extra_paths=["${jdk}/bin"],
    )
    output = generate(spec)
    assert "JAVABIN" in output
    assert "WARPATH" in output
    assert 'sed -i "s|JAVABIN|${jdk}/bin|g"' in output
    assert 'sed -i "s|WARPATH|$out/app/jenkins.war|g"' in output


# --- python-venv ---


def test_python_venv_requires_pip_packages():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="python-venv",
        source=Source(url="x", sha256="x"),
        exec_target="test",
    )
    with pytest.raises(ValueError, match="pip_packages"):
        generate(spec)


def test_python_venv_requires_exec_target():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="python-venv",
        source=Source(url="x", sha256="x"),
        pip_packages=["myapp"],
    )
    with pytest.raises(ValueError, match="exec_target"):
        generate(spec)


def test_python_venv_creates_venv():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="python-venv",
        pip_packages=["myapp", "gunicorn"],
        exec_target="myapp",
        source=Source(url="x", sha256="x"),
    )
    output = generate(spec)
    assert "python -m venv $out/venv" in output
    assert "pip install myapp gunicorn" in output
    assert 'sed -i "s|VENVBIN|$out/venv/bin|g"' in output


# --- nixpkgs-wrapper ---


def test_nixpkgs_wrapper_requires_package():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        template="nixpkgs-wrapper",
        source=Source(url="x", sha256="x"),
        exec_target="test",
    )
    with pytest.raises(ValueError, match="nixpkgs_package"):
        generate(spec)


def test_nixpkgs_wrapper_requires_exec_target():
    spec = AppSpec(
        pname="test",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="mypkg",
        source=Source(url="x", sha256="x"),
    )
    with pytest.raises(ValueError, match="exec_target"):
        generate(spec)


def test_nixpkgs_wrapper_inherits_version():
    spec = AppSpec(
        pname="radicale",
        version="",  # inherited from pkg
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="radicale",
        exec_target="radicale",
        source=Source(url="x", sha256="x"),
    )
    output = generate(spec)
    # Should use the package's version, not a hardcoded string
    assert "version = radicale.version" in output


def test_nixpkgs_wrapper_no_source_fetch():
    spec = AppSpec(
        pname="radicale",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="radicale",
        exec_target="radicale",
        source=Source(url="x", sha256="x"),
    )
    output = generate(spec)
    assert "dontUnpack = true" in output
    assert "fetchurl" not in output
