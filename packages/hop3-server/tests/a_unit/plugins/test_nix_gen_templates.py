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


def test_nixpkgs_wrapper_install_extra_emitted_raw():
    """install-extra is appended to installPhase without nix_escape, so
    that ${pkg} references interpolate at Nix build time."""
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="keycloak",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        install_extra="cp -R ${keycloak}/. $out/keycloak-home/",
    )
    output = generate(spec)
    assert "# --- install-extra" in output
    # Nix let-binding reference must NOT be escaped — it has to
    # interpolate at build time.
    assert "cp -R ${keycloak}/. $out/keycloak-home/" in output
    # Must come after the wrapper is emitted but before runtime.json.
    wrapper_end = output.find("chmod +x $out/bin/keycloak")
    install_extra = output.find("# --- install-extra")
    runtime_json = output.find("$out/hop3/runtime.json")
    assert wrapper_end < install_extra < runtime_json


def test_nixpkgs_wrapper_exec_prefix_replaces_pkgbin():
    """exec-prefix redirects PKGBIN to an arbitrary path under $out,
    so install-extra recipes can bake a runnable tree at package time."""
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="keycloak",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        exec_prefix="$out/keycloak-home/bin",
    )
    output = generate(spec)
    assert "s|PKGBIN|$out/keycloak-home/bin|g" in output
    # Default substitution must not be emitted when exec-prefix is set.
    assert "s|PKGBIN|${keycloak}/bin|g" not in output


def test_nixpkgs_wrapper_default_pkgbin_when_no_exec_prefix():
    """Without exec-prefix, PKGBIN resolves to ${<binding>}/bin as before."""
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
    assert "s|PKGBIN|${radicale}/bin|g" in output


def test_nixpkgs_wrapper_without_overrides_uses_plain_package():
    """Empty nixpkgs_overrides => `binding = pkgs.<pkg>;` (no .override)."""
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
    assert "radicale = pkgs.radicale;" in output
    assert ".override" not in output


def test_nixpkgs_wrapper_emits_override_when_overrides_present():
    """nixpkgs_overrides dict emits pkgs.X.override { ... } in the let block."""
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="keycloak",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        nixpkgs_overrides={
            "confFile": 'pkgs.writeText "keycloak.conf" "db=postgres\\n"',
        },
    )
    output = generate(spec)
    assert "keycloak = pkgs.keycloak.override {" in output
    # Value is emitted raw — pkgs.writeText reference must survive.
    assert 'confFile = pkgs.writeText "keycloak.conf" "db=postgres\\n";' in output


def test_nixpkgs_wrapper_overrides_multiple_keys():
    """Each override key renders on its own line inside the braces."""
    spec = AppSpec(
        pname="jenkins",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="jenkins",
        exec_target="jenkins.sh",
        source=Source(url="x", sha256="x"),
        nixpkgs_overrides={
            "extraJavaOpts": '"-Dfoo=bar"',
            "plugins": "[]",
        },
    )
    output = generate(spec)
    assert "jenkins = pkgs.jenkins.override {" in output
    assert 'extraJavaOpts = "-Dfoo=bar";' in output
    assert "plugins = [];" in output


def test_nixpkgs_wrapper_writable_home_emits_lazy_cp_prelude():
    """writable-home-at-runtime emits a `cp -rL … $HOME_DIR` prelude
    with a .hop3-ready marker so the copy runs once per app instance."""
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="keycloak",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        writable_home_at_runtime=True,
    )
    output = generate(spec)
    assert 'HOME_DIR="$PWD/.keycloak-home"' in output
    assert 'if [ ! -f "$HOME_DIR/.hop3-ready" ]; then' in output
    # ${keycloak}/. must Nix-interpolate (no `''$` escape), since it
    # resolves at build time to the read-only source the wrapper
    # copies from.
    assert 'cp -rL --no-preserve=ownership ${keycloak}/. "$HOME_DIR"' in output
    assert 'chmod -R u+w "$HOME_DIR"' in output
    assert 'touch "$HOME_DIR/.hop3-ready"' in output


def test_nixpkgs_wrapper_writable_home_env_var_exported():
    """writable-home-env-var exports the resolved path so the app
    (e.g., kc.sh reading KC_HOME_DIR) picks up the writable copy."""
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="keycloak",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        writable_home_at_runtime=True,
        writable_home_env_var="KC_HOME_DIR",
    )
    output = generate(spec)
    assert 'export KC_HOME_DIR="$HOME_DIR"' in output


def test_nixpkgs_wrapper_writable_home_pkgbin_resolved_at_runtime():
    """With writable-home, PKGBIN in the exec line must resolve to
    `$HOME_DIR/bin` at wrapper-run time (not at Nix-build time).
    That means the sed command has to emit `$HOME_DIR/bin` literally
    into the wrapper — which in turn means the Nix `''` string must
    carry `\\$HOME_DIR/bin` so the shell running sed sees the escape
    and preserves the `$`."""
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="keycloak",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        writable_home_at_runtime=True,
    )
    output = generate(spec)
    assert r'sed -i "s|PKGBIN|\$HOME_DIR/bin|g"' in output
    # The exec line in the wrapper body should reference the sed
    # placeholder (not the store path binding) — the sed replaces
    # PKGBIN → \$HOME_DIR/bin at nix-build time, and bash expands
    # $HOME_DIR at wrapper-run time.
    assert "exec PKGBIN/kc.sh" in output


def test_nixpkgs_wrapper_let_extra_emits_bindings():
    """let-extra adds lines to the Nix let-block, below the primary
    binding. Values are emitted raw so they evaluate at Nix build time."""
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="keycloak",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        let_extra={"jdk": "pkgs.zulu21"},
    )
    output = generate(spec)
    assert "keycloak = pkgs.keycloak;" in output
    assert "jdk = pkgs.zulu21;" in output
    # Order: primary binding comes first; let-extra after.
    assert output.index("keycloak = pkgs.keycloak;") < output.index(
        "jdk = pkgs.zulu21;"
    )


def test_nixpkgs_wrapper_env_exports_raw_interpolates_nix_refs():
    """env-exports-raw values are NOT nix_escape'd, so ${jdk}-style
    references reach Nix unescaped and interpolate at build time."""
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="keycloak",
        exec_target=".kc.sh-wrapped",
        source=Source(url="x", sha256="x"),
        let_extra={"jdk": "pkgs.zulu21"},
        env_exports_raw={"JAVA_HOME": "${jdk}"},
    )
    output = generate(spec)
    # Must survive into the wrapper body without `''$` escaping.
    assert 'export JAVA_HOME="${jdk}"' in output
    # Sanity: the nix_escape'd variant (what env-exports produces)
    # would emit `''${jdk}` — that must NOT appear for this value.
    assert "''${jdk}" not in output.split("export JAVA_HOME")[1][:30]


def test_nixpkgs_wrapper_writable_home_respects_explicit_exec_prefix():
    """If the user sets exec-prefix, it wins over the writable-home
    default (e.g., for apps whose runnable sits somewhere other than
    $HOME_DIR/bin inside the writable tree)."""
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        template="nixpkgs-wrapper",
        nixpkgs_package="keycloak",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        writable_home_at_runtime=True,
        exec_prefix="$HOME_DIR/custom/bin",
    )
    output = generate(spec)
    assert "s|PKGBIN|$HOME_DIR/custom/bin|g" in output
