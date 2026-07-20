# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Tests for individual template output correctness.

Goes beyond smoke tests to verify structural properties of the generated
Nix expressions: correct heredoc termination, placeholder presence,
sed commands, and Nix syntax structure.
"""

from __future__ import annotations

from typing import Any

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


def _python_spec(**overrides) -> AppSpec:
    defaults = {
        "pname": "test",
        "version": "1.0",
        "description": "t",
        "template": "python-venv",
        "source": Source(url="x", sha256="x"),
        "exec_target": "myapp",
        "pip_requirements": "requirements.txt",
        "pip_deps_hash": "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    }
    return AppSpec(**{**defaults, **overrides})


def test_python_venv_requires_a_lockfile():
    """Bare package names are unpinned: refuse rather than build irreproducibly."""
    with pytest.raises(ValueError, match="hash-pinned lockfile"):
        generate(_python_spec(pip_requirements=None))


def test_python_venv_requires_deps_hash():
    """Without the vendored-deps hash the dependency set is not pinned."""
    with pytest.raises(ValueError, match="pip-deps-hash"):
        generate(_python_spec(pip_deps_hash=None))


def test_python_venv_requires_exec_target():
    with pytest.raises(ValueError, match="exec_target"):
        generate(_python_spec(exec_target=None))


def test_python_venv_creates_venv():
    output = generate(_python_spec())
    assert "python -m venv $out/venv" in output
    assert 'sed -i "s|VENVBIN|$out/venv/bin|g"' in output


def test_python_venv_is_hermetic():
    """The build must be sandboxed and offline — the whole point of the template.

    Network access is confined to the fixed-output derivation that vendors the
    wheels; the application build then installs with --no-index.
    """
    output = generate(_python_spec())
    # the app build must NOT escape the sandbox
    assert "__noChroot = true" not in output
    # dependencies pinned by a content hash (the vendorHash analogue)
    assert 'outputHashMode = "recursive"' in output
    assert "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=" in output
    # and installed offline, verified against the lockfile hashes
    assert "--no-index" in output
    assert "--require-hashes" in output


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


class TestNodePnpmInstallTemplate:
    """node-pnpm-install is for Node apps whose runtime code assumes
    pnpm's virtual-store layout — npm's flat install breaks named ESM
    imports of CJS modules. Template seeds a package.json + runs
    pnpm install --prod inside the Nix build (__noChroot for network)."""

    def _base_spec(self, **kwargs):
        defaults: dict[str, Any] = {
            "pname": "directus",
            "version": "11.17.2",
            "description": "Headless CMS",
            "template": "node-pnpm-install",
            "nixpkgs_package": "directus",  # reinterpreted as npm package name
            "exec_target": "directus",
            "source": Source(url="x", sha256="x"),
        }
        defaults.update(kwargs)
        return AppSpec(**defaults)

    def test_requires_npm_package(self):
        spec = self._base_spec(nixpkgs_package=None)
        with pytest.raises(ValueError, match="nixpkgs_package"):
            generate(spec)

    def test_requires_exec_target(self):
        spec = self._base_spec(exec_target=None)
        with pytest.raises(ValueError, match="exec_target"):
            generate(spec)

    def test_requires_version(self):
        spec = self._base_spec(version="")
        with pytest.raises(ValueError, match="version"):
            generate(spec)

    def test_uses_pnpm_and_nochroot(self):
        """pnpm install needs network (nixpkgs-wrapper's closed sandbox
        wouldn't allow it), and pnpm_9 must be on nativeBuildInputs."""
        spec = self._base_spec()
        output = generate(spec)
        assert "__noChroot = true" in output
        assert "pkgs.pnpm_9" in output
        assert "pnpm install" in output
        assert "--prod" in output
        # `--package-import-method=copy` is the EPERM workaround.
        assert "package-import-method=copy" in output

    def test_default_node_version_is_22(self):
        """Directus-class apps all want Node 22. Default makes the
        common case boilerplate-free; `runtime_package` overrides."""
        spec = self._base_spec()
        output = generate(spec)
        assert "pkgs.nodejs_22" in output

    def test_runtime_package_override(self):
        spec = self._base_spec(runtime_package="nodejs_20")
        output = generate(spec)
        assert "pkgs.nodejs_20" in output

    def test_extras_via_pip_packages_slot(self):
        """pip_packages is reused as the 'additional npm packages' slot
        (semantically: extras alongside the primary). DB drivers are
        the typical case."""
        spec = self._base_spec(pip_packages=["pg@^8.11.0"])
        output = generate(spec)
        assert '"pg": "^8.11.0"' in output
        assert '"directus": "11.17.2"' in output

    def test_wrapper_pinned_node_on_path(self):
        """pnpm bin shims and npm-distributed binaries shebang
        `#!/usr/bin/env node`. Host's system Node may be too old for
        modern apps (directus 11 on Debian's Node 18 is the canonical
        typebox ESM/CJS failure). Wrapper must prepend the Nix-built
        Node to PATH, via a `NODEBIN` placeholder sed-replaced at
        install time."""
        spec = self._base_spec()
        output = generate(spec)
        # The PATH prepend line must live in the wrapper body (post-shebang).
        # NODEBIN is a build-time placeholder; `''${PATH}` is the Nix escape
        # that survives into the generated shell file as literal `${PATH}`
        # for bash to resolve at runtime.
        assert "export PATH=\"NODEBIN:''${PATH}\"" in output
        assert 'sed -i "s|NODEBIN|${nodejs}/bin|g"' in output

    def test_wrapper_exports_appdir(self):
        """`$out` is only defined inside the Nix build sandbox; it's
        empty at wrapper runtime. Pre-exec lines that need a path to
        the installed tree must use `$APPDIR`, which the wrapper
        exports (sed-replaced to `$out/app` at build time)."""
        spec = self._base_spec()
        output = generate(spec)
        # The wrapper must export APPDIR = <build-time-substituted path>.
        assert 'APPDIR="APPDIR_PLACEHOLDER"' in output
        assert "export APPDIR" in output
        # Install phase sed-replaces APPDIR_PLACEHOLDER with $out/app.
        assert 'sed -i "s|APPDIR_PLACEHOLDER|$out/app|g"' in output

    def test_exec_line_uses_runtime_appdir(self):
        """Exec line targets `$APPDIR/node_modules/.bin/<exec>` — the
        runtime-expanded variable, not a build-time placeholder. This
        way the same mechanism covers pre-exec commands in the user's
        hop3.toml (e.g., `$APPDIR/node_modules/.bin/directus bootstrap`)."""
        spec = self._base_spec(exec_target="directus", exec_args=["start"])
        output = generate(spec)
        assert "$APPDIR/node_modules/.bin/directus start" in output


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
