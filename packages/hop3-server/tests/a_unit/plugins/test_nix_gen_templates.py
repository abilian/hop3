# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Tests for individual template output correctness.

Goes beyond smoke tests to verify structural properties of the generated
Nix expressions: correct heredoc termination, placeholder presence,
sed commands, and Nix syntax structure.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import tomllib

from hop3.plugins.build.nix.gen.registry import generate
from hop3.plugins.build.nix.gen.spec import (
    AppSpec,
    FileMapping,
    GoSourcePayload,
    JavaGradlePayload,
    JavaWarPayload,
    NixpkgsWrapperPayload,
    NodePnpmInstallPayload,
    PhpAppPayload,
    PrebuiltArchivePayload,
    PrebuiltBinaryPayload,
    PythonVenvPayload,
    RubyBundlerPayload,
    Source,
)
from hop3.plugins.build.nix.gen.templates.node_pnpm_install import (
    lockfile_version_for,
    parse_lockfile_version,
)
from hop3.plugins.build.nix.gen.toml_adapter import app_spec_from_config

from .conftest import spec_for

# --- prebuilt-binary ---


def test_prebuilt_binary_requires_binary_name():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        source=Source(url="x", sha256="x", executable=True),
        payload=PrebuiltBinaryPayload(),
    )
    with pytest.raises(ValueError, match="binary_name"):
        generate(spec)


def test_prebuilt_binary_sed_replaces_bindir():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        source=Source(url="x", sha256="x", executable=True),
        payload=PrebuiltBinaryPayload(
            binary_name="test",
        ),
    )
    output = generate(spec)
    assert 'sed -i "s|BINDIR|$out/bin|g"' in output


def test_prebuilt_binary_wrapper_heredoc_terminated():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        source=Source(url="x", sha256="x", executable=True),
        payload=PrebuiltBinaryPayload(
            binary_name="test",
        ),
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
        exec_args=["serve", "--flag"],
        source=Source(url="x", sha256="x", executable=True),
        payload=PrebuiltBinaryPayload(
            binary_name="mybin",
        ),
    )
    output = generate(spec)
    assert "exec BINDIR/mybin serve --flag" in output


# --- prebuilt-archive ---


def test_prebuilt_archive_requires_exec_target():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        payload=PrebuiltArchivePayload(
            file_mappings=[FileMapping(source="bin/x", destination="bin/")],
        ),
    )
    with pytest.raises(ValueError, match="exec_target"):
        generate(spec)


def test_prebuilt_archive_requires_file_mappings():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        exec_target="mybin",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        payload=PrebuiltArchivePayload(),
    )
    with pytest.raises(ValueError, match="file_mappings"):
        generate(spec)


def test_prebuilt_archive_zip_has_unzip():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        exec_target="mybin",
        source=Source(url="x", sha256="x", archive="zip"),
        source_root=".",
        payload=PrebuiltArchivePayload(
            file_mappings=[FileMapping(source="bin/x", destination="bin/")],
        ),
    )
    output = generate(spec)
    assert "pkgs.unzip" in output
    assert "unzip $src" in output


def test_prebuilt_archive_sed_replaces_sharedir():
    spec = AppSpec(
        pname="myapp",
        version="1.0",
        description="t",
        exec_target="mybin",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        source_root="myapp",
        payload=PrebuiltArchivePayload(
            file_mappings=[FileMapping(source="bin/x", destination="bin/")],
        ),
    )
    output = generate(spec)
    assert 'sed -i "s|SHAREDIR|$out/share/myapp|g"' in output


# --- php-app ---


def test_php_app_single_file():
    spec = AppSpec(
        pname="adminer",
        version="4.8.1",
        description="t",
        source=Source(url="x", sha256="x"),
        extra_paths=["${php}/bin"],
        payload=PhpAppPayload(
            php_extensions=["mysqli"],
            single_file=True,
        ),
    )
    output = generate(spec)
    assert "dontUnpack = true" in output
    assert "cp $src $out/app/index.php" in output


def _composer_spec(**overrides) -> AppSpec:
    defaults = {
        "pname": "bookstack",
        "version": "1.0",
        "description": "t",
        "php_extensions": ["mysqli"],
        "needs_composer": True,
        "composer_deps_hash": "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "source": Source(url="x", sha256="x", archive="tar-gz"),
        "extra_paths": ["${php}/bin"],
    }
    return spec_for(PhpAppPayload, **{**defaults, **overrides})


def test_php_app_composer():
    output = generate(_composer_spec())
    assert "buildComposerProject" in output
    assert "${composerProject}/share/php/bookstack/. $out/app/" in output


def test_php_app_install_files_shipped_from_recipe_dir():
    """
    install-files ships recipe-local aux scripts into $out/app (e.g. WordPress's
    wp-install.php, which is absent from the upstream tarball) via a `${./<f>}`
    nix path that resolves against the recipe dir. Lets a pre-exec install reuse
    a reviewable script file instead of re-encoding install logic inline.
    """
    spec = spec_for(
        PhpAppPayload,
        pname="wordpress",
        version="6.4.2",
        description="t",
        php_extensions=["mysqli"],
        source=Source(url="x", sha256="x", archive="tar-gz"),
        extra_paths=["${php}/bin"],
        install_files=["wp-install.php", "scripts/helper.php"],
    )
    output = generate(spec)
    assert "install -D ${./wp-install.php} $out/app/wp-install.php" in output
    assert "install -D ${./scripts/helper.php} $out/app/scripts/helper.php" in output


def test_php_app_composer_requires_deps_hash():
    """Without the vendorHash the dependency set is unpinned — refuse."""
    with pytest.raises(ValueError, match="composer-deps-hash"):
        generate(_composer_spec(composer_deps_hash=None))


def test_php_app_composer_is_hermetic():
    """
    buildComposerProject compiles from source, offline, in the sandbox.

    The earlier hand-rolled FOD vendoring composer's output tree was invalid —
    a fixed-output derivation may not reference store paths, but composer bin
    proxies reference bash. buildComposerProject is the nixpkgs builder that
    handles this correctly (the composer analogue of buildGoModule).
    """
    output = generate(_composer_spec())
    assert "__noChroot = true" not in output
    assert 'vendorHash = "sha256-' in output
    assert "composerNoDev = true" in output
    # the invalid hand-rolled FOD approach must be gone
    assert "composerVendor" not in output
    assert "outputHashMode" not in output


def test_php_app_composer_failure_is_not_swallowed():
    """`|| true` would ship an app with a partial vendor tree as a success."""
    output = generate(_composer_spec())
    assert "|| true" not in output


def test_php_app_composer_strict_validation_defaults_on():
    """
    buildComposerProject validates composer.json by default; don't weaken it
    unless a recipe opts out explicitly.
    """
    output = generate(_composer_spec())
    assert "composerStrictValidation" not in output


def test_php_app_composer_strict_validation_opt_out():
    """
    A third-party release that fails composer's pedantic validate can skip it
    explicitly (recorded per app), but only when asked.
    """
    output = generate(_composer_spec(composer_strict_validation=False))
    assert "composerStrictValidation = false" in output


def test_php_app_artisan_serve():
    spec = AppSpec(
        pname="laravel-app",
        version="1.0",
        description="t",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        extra_paths=["${php}/bin"],
        payload=PhpAppPayload(
            php_extensions=[],
            serve_mode="artisan",
        ),
    )
    output = generate(spec)
    assert "artisan serve" in output
    assert "--host=0.0.0.0" in output


def test_php_app_web_root():
    spec = AppSpec(
        pname="dolibarr",
        version="1.0",
        description="t",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        extra_paths=["${php}/bin"],
        payload=PhpAppPayload(
            php_extensions=[],
            web_root="htdocs",
        ),
    )
    output = generate(spec)
    assert "APPDIR/htdocs" in output


def test_php_app_sed_replaces_phpbin():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        source=Source(url="x", sha256="x", archive="tar-gz"),
        extra_paths=["${php}/bin"],
        payload=PhpAppPayload(
            php_extensions=[],
        ),
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
        source=Source(url="x", sha256="x", archive="zip"),
        source_root="limesurvey",
        extra_paths=["${php}/bin"],
        payload=PhpAppPayload(
            php_extensions=[],
        ),
    )
    output = generate(spec)
    assert "cp -r limesurvey/. $out/app/" in output


# --- java-gradle ---


def _gradle_spec(**overrides) -> AppSpec:
    defaults: dict[str, Any] = {
        "pname": "stirling-pdf",
        "version": "0.33.1",
        "description": "PDF toolkit",
        "source": Source(url="https://x/src.tar.gz", sha256="x", archive="tar-gz"),
        "jar_glob": "build/libs/Stirling-PDF-*.jar",
        "jar_name": "Stirling-PDF.jar",
    }
    defaults.update(overrides)
    return spec_for(JavaGradlePayload, **defaults)


def test_java_gradle_requires_jar():
    with pytest.raises(ValueError, match="gradle-jar-glob"):
        generate(_gradle_spec(jar_glob=None))


def test_java_gradle_builds_from_source_offline():
    """
    Compiled by Gradle with the dep set pinned by a committed deps.json —
    not a downloaded jar/dist, not a nixpkgs wrap.
    """
    out = generate(
        _gradle_spec(
            patches=["fix.patch"],
            flags=["-x", "spotlessApply"],
        )
    )
    assert "gradle.fetchDeps" in out
    assert "data = ./deps.json" in out
    assert "patches = [ ./fix.patch ];" in out
    assert 'gradleFlags = [ "-x" "spotlessApply" ];' in out
    assert "install -Dm644 build/libs/Stirling-PDF-*.jar $out/Stirling-PDF.jar" in out
    assert "java $JAVA_OPTS -jar" in out
    assert "doCheck = false" in out


# --- java-war ---


def test_java_war_requires_war_file():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="t",
        source=Source(url="x", sha256="x"),
        payload=JavaWarPayload(),
    )
    with pytest.raises(ValueError, match="war_file"):
        generate(spec)


def test_java_war_sed_replaces_javabin_and_warpath():
    spec = AppSpec(
        pname="jenkins",
        version="1.0",
        description="t",
        runtime_package="jdk17",
        source=Source(url="x", sha256="x"),
        extra_paths=["${jdk}/bin"],
        payload=JavaWarPayload(
            war_file="jenkins.war",
        ),
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
        "source": Source(url="x", sha256="x"),
        "exec_target": "myapp",
        "requirements": "requirements.txt",
        "deps_hash": "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    }
    return spec_for(PythonVenvPayload, **{**defaults, **overrides})


def test_python_venv_requires_a_lockfile():
    """Bare package names are unpinned: refuse rather than build irreproducibly."""
    with pytest.raises(ValueError, match="hash-pinned lockfile"):
        generate(_python_spec(requirements=None))


def test_python_venv_requires_deps_hash():
    """Without the vendored-deps hash the dependency set is not pinned."""
    with pytest.raises(ValueError, match="pip-deps-hash"):
        generate(_python_spec(deps_hash=None))


def test_python_venv_requires_exec_target():
    with pytest.raises(ValueError, match="exec_target"):
        generate(_python_spec(exec_target=None))


def test_python_venv_creates_venv():
    output = generate(_python_spec())
    assert "python -m venv $out/venv" in output
    assert 'sed -i "s|VENVBIN|$out/venv/bin|g"' in output


def test_python_venv_strips_c_extensions_for_reproducibility():
    """
    A C extension embeds pip's random build dir as the DWARF comp_dir, so two
    builds differ byte-for-byte. The template must strip debug info AND rewrite
    the wheel RECORD to match — removing either half reintroduces the drift
    (strip without RECORD-fix leaves the pre-strip hash in RECORD).

    The strip must be SURGICAL — guarded by the `/build/pip-` marker so it only
    touches sdist-built extensions. Re-stripping prebuilt-wheel native libs
    (Rust cdylibs, mypyc modules) broke bugsink at runtime; those are already
    reproducible and must be left untouched.
    """
    output = generate(_python_spec())
    assert "strip --strip-debug" in output
    assert "grep -qa '/build/pip-'" in output  # surgical guard, not a blanket strip
    assert "RECORD" in output
    assert "sha256=" in output  # the RECORD hash is recomputed post-strip


def test_python_venv_is_hermetic():
    """
    The build must be sandboxed and offline — the whole point of the template.

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
        source=Source(url="x", sha256="x"),
        exec_target="test",
        payload=NixpkgsWrapperPayload(),
    )
    with pytest.raises(ValueError, match="nixpkgs_package"):
        generate(spec)


def test_nixpkgs_wrapper_requires_exec_target():
    spec = AppSpec(
        pname="test",
        version="",
        description="t",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="mypkg",
        ),
    )
    with pytest.raises(ValueError, match="exec_target"):
        generate(spec)


def test_nixpkgs_wrapper_inherits_version():
    spec = AppSpec(
        pname="radicale",
        version="",  # inherited from pkg
        description="t",
        exec_target="radicale",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="radicale",
        ),
    )
    output = generate(spec)
    # Should use the package's version, not a hardcoded string
    assert "version = radicale.version" in output


def test_nixpkgs_wrapper_no_source_fetch():
    spec = AppSpec(
        pname="radicale",
        version="",
        description="t",
        exec_target="radicale",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="radicale",
        ),
    )
    output = generate(spec)
    assert "dontUnpack = true" in output
    assert "fetchurl" not in output


def test_nixpkgs_wrapper_install_extra_emitted_raw():
    """
    install-extra is appended to installPhase without nix_escape, so
    that ${pkg} references interpolate at Nix build time.
    """
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="keycloak",
            install_extra="cp -R ${keycloak}/. $out/keycloak-home/",
        ),
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
    """
    exec-prefix redirects PKGBIN to an arbitrary path under $out,
    so install-extra recipes can bake a runnable tree at package time.
    """
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="keycloak",
            exec_prefix="$out/keycloak-home/bin",
        ),
    )
    output = generate(spec)
    assert "s|PKGBIN|$out/keycloak-home/bin|g" in output
    # Default substitution must not be emitted when exec-prefix is set.
    assert "s|PKGBIN|${keycloak}/bin|g" not in output


class TestNodePnpmInstallTemplate:
    """
    node-pnpm-install is for Node apps whose runtime code assumes
    pnpm's virtual-store layout — npm's flat install breaks named ESM
    imports of CJS modules. Dependencies are fetched by a fixed-output
    derivation from a committed lockfile; the app build is offline.
    """

    def _base_spec(self, **kwargs):
        defaults: dict[str, Any] = {
            "pname": "directus",
            "version": "11.17.2",
            "description": "Headless CMS",
            "npm_package": "directus",  # reinterpreted as npm package name
            "exec_target": "directus",
            "manifest": "package.json",
            "lockfile": "pnpm-lock.yaml",
            "deps_hash": "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            "source": Source(url="x", sha256="x"),
        }
        defaults.update(kwargs)
        return spec_for(NodePnpmInstallPayload, **defaults)

    def test_requires_a_committed_lockfile(self):
        """A build-time-synthesized manifest cannot be locked."""
        with pytest.raises(ValueError, match="committed manifest and lockfile"):
            generate(self._base_spec(lockfile=None))

    def test_requires_deps_hash(self):
        with pytest.raises(ValueError, match="node-deps-hash"):
            generate(self._base_spec(deps_hash=None))

    def test_is_hermetic(self):
        """Deps come from the fetched store; the app build never hits the network."""
        output = generate(self._base_spec())
        assert "__noChroot = true" not in output
        assert 'outputHashMode = "recursive"' in output
        assert "pnpm fetch --store-dir" in output
        assert "--offline" in output
        assert "--frozen-lockfile" in output
        # postinstall hooks routinely fetch prebuilt binaries
        assert "--ignore-scripts" in output

    def test_requires_npm_package(self):
        spec = self._base_spec(npm_package=None)
        with pytest.raises(ValueError, match="npm-package"):
            generate(spec)

    def test_requires_exec_target(self):
        spec = self._base_spec(exec_target=None)
        with pytest.raises(ValueError, match="exec_target"):
            generate(spec)

    def test_requires_version(self):
        spec = self._base_spec(version="")
        with pytest.raises(ValueError, match="version"):
            generate(spec)

    def test_uses_pnpm_inside_the_sandbox(self):
        """pnpm_9 must be on nativeBuildInputs, and the install stays offline."""
        spec = self._base_spec()
        output = generate(spec)
        assert "pkgs.pnpm_9" in output
        assert "pnpm install" in output
        assert "--prod" in output
        # `--package-import-method=copy` is the EPERM workaround.
        assert "package-import-method=copy" in output

    def test_pnpm_store_is_normalized_for_reproducibility(self):
        """
        `pnpm fetch` stamps a `checkedAt` timestamp into each store index and
        leaves key order unstable, so the FOD hash drifts. The FOD must strip
        `checkedAt` and sort keys (as nixpkgs' own pnpm.fetchDeps does) or the
        vendorHash fails on any rebuild.
        """
        output = generate(self._base_spec())
        assert "checkedAt" in output
        assert "--sort-keys" in output

    def test_pnpm_store_skips_stdenv_fixup(self):
        """
        stdenv's fixupPhase runs patchShebangs over the vendored store,
        rewriting npm scripts' `#!/usr/bin/env bash` to an absolute
        `/nix/store/…-bash` path — a store reference a fixed-output derivation
        may not contain. The store FOD must set dontFixup to keep the vendored
        bytes untouched.
        """
        output = generate(self._base_spec())
        assert "dontFixup = true" in output

    def test_pnpm_app_strips_prunedat_timestamp(self):
        """
        pnpm stamps a `prunedAt` wall-clock timestamp into
        node_modules/.modules.yaml, so two installs of the identical store
        differ by that line. The app build must strip it to stay reproducible.
        """
        output = generate(self._base_spec())
        assert "prunedAt" in output
        assert ".modules.yaml" in output

    def test_no_native_packages_stays_sealed(self):
        """
        The default install runs --ignore-scripts and adds no compiler
        toolchain — nothing is built from source unless a recipe opts in.
        """
        output = generate(self._base_spec())
        assert "pnpm rebuild" not in output
        assert "pkgs.gcc" not in output
        assert "npm_config_nodedir" not in output

    def test_native_packages_compiled_offline_from_source(self):
        """
        A declared node-gyp addon is rebuilt from source, offline, with the
        C/C++ toolchain and the pinned Node's headers — the sealed
        --ignore-scripts install alone leaves it uncompiled (directus'
        isolated-vm MODULE_NOT_FOUND).
        """
        output = generate(self._base_spec(native_packages=["isolated-vm"]))
        # toolchain on the app derivation
        assert "pkgs.python3 pkgs.gnumake pkgs.gcc" in output
        # node headers + offline rebuild of exactly the declared package
        assert "npm_config_nodedir=${nodejs}" in output
        assert "pnpm rebuild --store-dir ${pnpmStore} isolated-vm" in output
        # still fetched from the pinned store, never the network
        assert "--offline" in output

    def test_multiple_native_packages_rebuilt_together(self):
        output = generate(self._base_spec(native_packages=["isolated-vm", "sharp"]))
        assert "pnpm rebuild --store-dir ${pnpmStore} isolated-vm sharp" in output

    def test_default_node_version_is_22(self):
        """
        Directus-class apps all want Node 22. Default makes the
        common case boilerplate-free; `runtime_package` overrides.
        """
        spec = self._base_spec()
        output = generate(spec)
        assert "pkgs.nodejs_22" in output

    def test_runtime_package_override(self):
        spec = self._base_spec(runtime_package="nodejs_20")
        output = generate(spec)
        assert "pkgs.nodejs_20" in output

    def test_dependencies_come_from_the_committed_manifest(self):
        """
        Extras are no longer injected via a synthesized package.json.

        The old `pip-packages`-as-npm-extras slot produced a manifest that
        existed only inside the build, so it could never be locked. Additional
        dependencies now belong in the committed manifest alongside the rest;
        the key itself is gone, and the adapter rejects it (see the adapter
        tests) rather than dropping it silently.
        """
        output = generate(self._base_spec())
        assert '"pg": "^8.11.0"' not in output
        assert "cp ${manifest} package.json" in output
        assert "cp ${lockfile} pnpm-lock.yaml" in output

    def test_wrapper_pinned_node_on_path(self):
        """
        pnpm bin shims and npm-distributed binaries shebang
        `#!/usr/bin/env node`. Host's system Node may be too old for
        modern apps (directus 11 on Debian's Node 18 is the canonical
        typebox ESM/CJS failure). Wrapper must prepend the Nix-built
        Node to PATH, via a `NODEBIN` placeholder sed-replaced at
        install time.
        """
        spec = self._base_spec()
        output = generate(spec)
        # The PATH prepend line must live in the wrapper body (post-shebang).
        # NODEBIN is a build-time placeholder; `''${PATH}` is the Nix escape
        # that survives into the generated shell file as literal `${PATH}`
        # for bash to resolve at runtime.
        assert "export PATH=\"NODEBIN:''${PATH}\"" in output
        assert 'sed -i "s|NODEBIN|${nodejs}/bin|g"' in output

    def test_wrapper_exports_appdir(self):
        """
        `$out` is only defined inside the Nix build sandbox; it's
        empty at wrapper runtime. Pre-exec lines that need a path to
        the installed tree must use `$APPDIR`, which the wrapper
        exports (sed-replaced to `$out/app` at build time).
        """
        spec = self._base_spec()
        output = generate(spec)
        # The wrapper must export APPDIR = <build-time-substituted path>.
        assert 'APPDIR="APPDIR_PLACEHOLDER"' in output
        assert "export APPDIR" in output
        # Install phase sed-replaces APPDIR_PLACEHOLDER with $out/app.
        assert 'sed -i "s|APPDIR_PLACEHOLDER|$out/app|g"' in output

    def test_exec_line_uses_runtime_appdir(self):
        """
        Exec line targets `$APPDIR/node_modules/.bin/<exec>` — the
        runtime-expanded variable, not a build-time placeholder. This
        way the same mechanism covers pre-exec commands in the user's
        hop3.toml (e.g., `$APPDIR/node_modules/.bin/directus bootstrap`).
        """
        spec = self._base_spec(exec_target="directus", exec_args=["start"])
        output = generate(spec)
        assert "$APPDIR/node_modules/.bin/directus start" in output


def test_nixpkgs_wrapper_default_pkgbin_when_no_exec_prefix():
    """Without exec-prefix, PKGBIN resolves to ${<binding>}/bin as before."""
    spec = AppSpec(
        pname="radicale",
        version="",
        description="t",
        exec_target="radicale",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="radicale",
        ),
    )
    output = generate(spec)
    assert "s|PKGBIN|${radicale}/bin|g" in output


def test_nixpkgs_wrapper_without_overrides_uses_plain_package():
    """Empty nixpkgs_overrides => `binding = pkgs.<pkg>;` (no .override)."""
    spec = AppSpec(
        pname="radicale",
        version="",
        description="t",
        exec_target="radicale",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="radicale",
        ),
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
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="keycloak",
            overrides={
                "confFile": 'pkgs.writeText "keycloak.conf" "db=postgres\\n"',
            },
        ),
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
        exec_target="jenkins.sh",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="jenkins",
            overrides={
                "extraJavaOpts": '"-Dfoo=bar"',
                "plugins": "[]",
            },
        ),
    )
    output = generate(spec)
    assert "jenkins = pkgs.jenkins.override {" in output
    assert 'extraJavaOpts = "-Dfoo=bar";' in output
    assert "plugins = [];" in output


def test_nixpkgs_wrapper_writable_home_emits_lazy_cp_prelude():
    """
    writable-home-at-runtime emits a `cp -rL … $HOME_DIR` prelude
    with a .hop3-ready marker so the copy runs once per app instance.
    """
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        writable_home_at_runtime=True,
        payload=NixpkgsWrapperPayload(
            package="keycloak",
        ),
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
    """
    writable-home-env-var exports the resolved path so the app
    (e.g., kc.sh reading KC_HOME_DIR) picks up the writable copy.
    """
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        writable_home_at_runtime=True,
        writable_home_env_var="KC_HOME_DIR",
        payload=NixpkgsWrapperPayload(
            package="keycloak",
        ),
    )
    output = generate(spec)
    assert 'export KC_HOME_DIR="$HOME_DIR"' in output


def test_nixpkgs_wrapper_writable_home_pkgbin_resolved_at_runtime():
    """
    With writable-home, PKGBIN in the exec line must resolve to
    `$HOME_DIR/bin` at wrapper-run time (not at Nix-build time).
    That means the sed command has to emit `$HOME_DIR/bin` literally
    into the wrapper — which in turn means the Nix `''` string must
    carry `\\$HOME_DIR/bin` so the shell running sed sees the escape
    and preserves the `$`.
    """
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        writable_home_at_runtime=True,
        payload=NixpkgsWrapperPayload(
            package="keycloak",
        ),
    )
    output = generate(spec)
    assert r'sed -i "s|PKGBIN|\$HOME_DIR/bin|g"' in output
    # The exec line in the wrapper body should reference the sed
    # placeholder (not the store path binding) — the sed replaces
    # PKGBIN → \$HOME_DIR/bin at nix-build time, and bash expands
    # $HOME_DIR at wrapper-run time.
    assert "exec PKGBIN/kc.sh" in output


def test_nixpkgs_wrapper_let_extra_emits_bindings():
    """
    let-extra adds lines to the Nix let-block, below the primary
    binding. Values are emitted raw so they evaluate at Nix build time.
    """
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="keycloak",
            let_extra={"jdk": "pkgs.zulu21"},
        ),
    )
    output = generate(spec)
    assert "keycloak = pkgs.keycloak;" in output
    assert "jdk = pkgs.zulu21;" in output
    # Order: primary binding comes first; let-extra after.
    assert output.index("keycloak = pkgs.keycloak;") < output.index(
        "jdk = pkgs.zulu21;"
    )


def test_nixpkgs_wrapper_env_exports_raw_interpolates_nix_refs():
    """
    env-exports-raw values are NOT nix_escape'd, so ${jdk}-style
    references reach Nix unescaped and interpolate at build time.
    """
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        exec_target=".kc.sh-wrapped",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(
            package="keycloak",
            let_extra={"jdk": "pkgs.zulu21"},
            env_exports_raw={"JAVA_HOME": "${jdk}"},
        ),
    )
    output = generate(spec)
    # Must survive into the wrapper body without `''$` escaping.
    assert 'export JAVA_HOME="${jdk}"' in output
    # Sanity: the nix_escape'd variant (what env-exports produces)
    # would emit `''${jdk}` — that must NOT appear for this value.
    assert "''${jdk}" not in output.split("export JAVA_HOME")[1][:30]


def test_nixpkgs_wrapper_writable_home_respects_explicit_exec_prefix():
    """
    If the user sets exec-prefix, it wins over the writable-home
    default (e.g., for apps whose runnable sits somewhere other than
    $HOME_DIR/bin inside the writable tree).
    """
    spec = AppSpec(
        pname="keycloak",
        version="",
        description="t",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        writable_home_at_runtime=True,
        payload=NixpkgsWrapperPayload(
            package="keycloak",
            exec_prefix="$HOME_DIR/custom/bin",
        ),
    )
    output = generate(spec)
    assert "s|PKGBIN|$HOME_DIR/custom/bin|g" in output


# --- go-source ---


def _go_spec(**overrides) -> AppSpec:
    defaults: dict[str, Any] = {
        "pname": "miniflux",
        "version": "2.2.8",
        "description": "Feed reader",
        "exec_target": "miniflux",
        "vendor_hash": "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "source": Source(url="https://x/src.tar.gz", sha256="x", archive="tar-gz"),
    }
    defaults.update(overrides)
    return spec_for(GoSourcePayload, **defaults)


def test_go_source_requires_vendor_hash():
    """A null vendorHash would let the build resolve modules from the network."""
    with pytest.raises(ValueError, match="go-vendor-hash"):
        generate(_go_spec(vendor_hash=None))


def test_go_source_requires_exec_target():
    with pytest.raises(ValueError, match="exec_target"):
        generate(_go_spec(exec_target=None))


def test_go_source_builds_from_source():
    """The point of the template: compile, don't download a binary."""
    output = generate(_go_spec())
    assert "buildGoModule" in output
    assert 'vendorHash = "sha256-AAAA' in output
    # never a prebuilt artefact
    assert "autoPatchelf" not in output
    assert "executable = true" not in output


def test_go_source_is_hermetic():
    output = generate(_go_spec())
    assert "__noChroot" not in output
    # upstream test suites often need network/a database
    assert "doCheck = false" in output


def test_go_source_optional_attrs_omitted_when_unset():
    output = generate(_go_spec())
    assert "subPackages" not in output
    assert "ldflags" not in output


def test_go_source_emits_optional_attrs():
    output = generate(_go_spec(sub_packages=["./cmd/app"], ldflags=["-s", "-w"]))
    assert 'subPackages = [ "./cmd/app" ];' in output
    assert 'ldflags = [ "-s" "-w" ];' in output


def test_go_source_proxy_vendor():
    """gitea/forgejo need proxyVendor to dodge the vendor/modules.txt check."""
    assert "proxyVendor = true;" not in generate(_go_spec())
    assert "proxyVendor = true;" in generate(_go_spec(proxy_vendor=True))


def test_go_source_go_version_override():
    """An app whose go.mod needs a newer Go than the pin's default overrides it."""
    assert "buildGoModule.override" not in generate(_go_spec())
    out = generate(_go_spec(go_version="go_1_24"))
    assert "pkgs.buildGoModule.override { go = pkgs.go_1_24; }" in out


def test_go_source_frontend():
    """
    A go-source app with a JS frontend builds it via buildNpmPackage and wires
    the assets to the wrapper as $HOP3_GO_FRONTEND.
    """
    out = generate(
        _go_spec(
            frontend_build="BROWSERSLIST_IGNORE_OLD_DATA=true npx webpack",
            npm_deps_hash="sha256-AAAA",
        )
    )
    assert "buildNpmPackage" in out
    assert 'npmDepsHash = "sha256-AAAA"' in out
    assert "BROWSERSLIST_IGNORE_OLD_DATA=true npx webpack" in out
    assert 'export HOP3_GO_FRONTEND="FRONTENDDIR"' in out
    assert 'sed -i "s|FRONTENDDIR|${frontend}|g"' in out


def test_go_source_frontend_requires_npm_hash():
    """Without the npmDepsHash the frontend's npm set is unpinned — refuse."""
    with pytest.raises(ValueError, match="go-npm-deps-hash"):
        generate(_go_spec(frontend_build="npx webpack"))


def test_go_source_pnpm_frontend():
    """
    A pnpm frontend (vikunja) builds via pnpm.fetchDeps + configHook, not
    buildNpmPackage.
    """
    out = generate(
        _go_spec(
            frontend_build="pnpm run build",
            frontend_pnpm=True,
            pnpm_deps_hash="sha256-BBBB",
        )
    )
    assert "pnpm_9.fetchDeps" in out
    assert "configHook" in out
    assert 'hash = "sha256-BBBB"' in out
    assert "buildNpmPackage" not in out


def test_go_source_pnpm_requires_pnpm_hash():
    with pytest.raises(ValueError, match="go-pnpm-deps-hash"):
        generate(_go_spec(frontend_build="pnpm run build", frontend_pnpm=True))


def test_go_source_embedded_frontend():
    """
    An app that `go:embed`s the frontend copies the built assets into the
    source before the Go compile (preBuild), with no disk-served wiring.
    """
    out = generate(
        _go_spec(
            frontend_build="pnpm run build",
            frontend_pnpm=True,
            pnpm_deps_hash="sha256-BBBB",
            frontend_output="dist",
            frontend_embed_path="frontend/dist",
        )
    )
    assert "preBuild" in out
    assert "cp -r ${frontend} frontend/dist" in out
    # embed mode: no runtime disk wiring
    assert "HOP3_GO_FRONTEND" not in out
    assert "FRONTENDDIR" not in out


# --- pnpm lockfile/pin compatibility ---


def test_pnpm_lockfile_versions_are_measured_not_guessed():
    """pnpm 9, 10 and 11 all emit 9.0; only pnpm 8 differs (6.0)."""
    assert lockfile_version_for("pnpm_8") == "6.0"
    assert lockfile_version_for("pnpm_9") == "9.0"
    assert lockfile_version_for("pnpm_11") == "9.0"
    assert lockfile_version_for("pnpm_99") is None


def test_parse_lockfile_version_handles_quoting():
    assert parse_lockfile_version("lockfileVersion: '9.0'\n\nsettings:\n") == "9.0"
    assert parse_lockfile_version("lockfileVersion: 6.0\n") == "6.0"
    assert parse_lockfile_version("settings:\n  x: 1\n") is None


def test_pnpm_pin_is_configurable():
    """The pin was hardcoded; a recipe may need a different major."""
    spec = AppSpec(
        pname="x",
        version="1.0",
        description="t",
        exec_target="x",
        source=Source(url="x", sha256="x"),
        payload=NodePnpmInstallPayload(
            npm_package="x",
            manifest="package.json",
            lockfile="pnpm-lock.yaml",
            deps_hash="sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            pnpm_package="pnpm_10",
        ),
    )
    assert "pkgs.pnpm_10" in generate(spec)


def test_committed_lockfiles_match_their_pinned_pnpm(catalog_apps):
    """
    Guard: a lockfile the pinned pnpm cannot read fails inside the Nix build
    with a parse error naming neither the pin nor the lockfile.

    Reads the catalog, via the shared fixture. It used to count
    `parents[5] / "apps"` to this repo's own tree, where the pnpm recipes lived
    until they moved to the catalog; the glob then matched nothing and the
    `checked` guard below is what said so, instead of a green vacuous pass.
    """
    assert catalog_apps.is_dir(), f"app corpus not found at {catalog_apps}"
    mismatches = {}
    checked = 0
    # `<status>/<app>/hop3.toml` — maturity decides the directory (ADR 059).
    for toml_path in catalog_apps.glob("*/*/hop3.toml"):
        text = toml_path.read_text()
        if 'template = "node-pnpm-install"' not in text:
            continue
        lock = toml_path.parent / "pnpm-lock.yaml"
        if not lock.is_file():
            continue
        checked += 1
        pin_match = re.search(
            r'^\s*node-pnpm-package\s*=\s*"([^"]+)"', text, re.MULTILINE
        )
        pin = pin_match.group(1) if pin_match else "pnpm_9"
        want = lockfile_version_for(pin)
        got = parse_lockfile_version(lock.read_text())
        if want != got:
            mismatches[toml_path.parent.name] = (
                f"pin {pin} wants {want}, lockfile is {got}"
            )
    assert checked, "no node-pnpm-install recipe with a lockfile found"
    assert mismatches == {}, f"lockfile/pnpm-pin mismatch: {mismatches}"


class TestGoSourceLocalApp:
    """
    A recipe with no `url` packages the directory it lives in.

    Ten of the eleven templates assume the application is fetched from
    somewhere — a release tarball, the npm registry, nixpkgs. That leaves a
    user's *own* code, the git-push case a PaaS exists for, with no nix-gen
    route at all. go-source is the first to close it.
    """

    def _spec(self, **kwargs):
        defaults = {
            "pname": "golang-minimal-gen",
            "version": "0.1.0",
            "description": "local go app",
            "exec_target": "golang-minimal",
            "vendor_hash": "none",
            "source": Source(url="", sha256=""),
        }
        defaults.update(kwargs)
        return spec_for(GoSourcePayload, **defaults)

    def test_no_url_builds_the_recipe_directory(self):
        output = generate(self._spec())
        assert "src = ./.;" in output
        assert "fetchurl" not in output

    def test_a_url_still_fetches(self):
        output = generate(
            self._spec(source=Source(url="https://x/src.tar.gz", sha256="x"))
        )
        assert "pkgs.fetchurl" in output
        assert "src = ./.;" not in output

    def test_no_dependencies_emits_a_null_vendor_hash(self):
        """
        `vendorHash = null` is correct for a module that requires nothing —
        there is no set to pin. Spelled explicitly so it stays a decision.
        """
        assert "vendorHash = null;" in generate(self._spec())

    def test_a_hash_is_still_quoted(self):
        out = generate(self._spec(vendor_hash="sha256-AAAA="))
        assert 'vendorHash = "sha256-AAAA=";' in out

    def test_omitting_the_hash_entirely_is_still_refused(self):
        """ "none" is a claim about the module; absence is an oversight."""
        with pytest.raises(ValueError, match="go-vendor-hash"):
            generate(self._spec(vendor_hash=None))


class TestGoStaticDirs:
    """
    Some Go apps resolve more than the built frontend under their static
    root. gitea/forgejo look up both `public/` and `options/` (locales,
    gitignores, licences) there; shipping only the built frontend left the
    locales missing and gitea died at boot registering a cron task
    ("translation is missing for task update_mirrors"), crash-looping under
    uwsgi rather than timing out — a failure a bigger start-timeout can't fix.
    """

    def _spec(self, **kwargs):
        defaults = {
            "pname": "gitea",
            "version": "1.22.6",
            "description": "git service",
            "exec_target": "gitea",
            "vendor_hash": "sha256-AAA=",
            "frontend_build": "npx webpack",
            "npm_deps_hash": "sha256-BBB=",
            "source": Source(url="x", sha256="x", archive="tar-gz"),
        }
        defaults.update(kwargs)
        return spec_for(GoSourcePayload, **defaults)

    def test_source_dirs_ship_into_the_static_root(self):
        output = generate(self._spec(static_dirs=["options"]))
        assert "cp -R public $out/" in output  # the built frontend
        assert "cp -R options $out/" in output  # the source assets

    def test_several_dirs(self):
        output = generate(self._spec(static_dirs=["options", "templates"]))
        assert "cp -R options $out/" in output
        assert "cp -R templates $out/" in output

    def test_absent_by_default(self):
        """Apps that need nothing extra emit nothing extra."""
        output = generate(self._spec())
        assert "cp -R options $out/" not in output

    def test_the_real_gitea_recipe_ships_options(self, catalog_recipe):
        """Regression on the recipe itself, not just the template."""
        config = tomllib.loads(
            (catalog_recipe("gitea-nixgen") / "hop3.toml").read_text()
        )
        spec = app_spec_from_config(config["nix"], config["metadata"], "gitea")
        assert "options" in spec.payload_as(GoSourcePayload).static_dirs


class TestRubyBundler:
    """
    ruby-bundler packages a real Ruby app from a pinned gem set. Rails
    specifics (writable home, generated config, migrations) are expressed by the
    recipe through the shared wrapper fields, not hardcoded in the template.
    """

    def _spec(self, **kwargs):
        defaults = {
            "pname": "redmine",
            "version": "5.1.10",
            "description": "project management",
            "exec_target": "rails",
            "source": Source(url="", sha256=""),
        }
        defaults.update(kwargs)
        return spec_for(RubyBundlerPayload, **defaults)

    def test_local_app_builds_from_the_recipe_dir(self):
        output = generate(self._spec())
        assert "src = ./.;" in output

    def test_packaged_app_fetches_a_pinned_tarball(self):
        """A released app is hash-pinned, not the recipe directory."""
        output = generate(
            self._spec(
                source=Source(
                    url="https://x/redmine.tar.gz", sha256="abc", archive="tar-gz"
                )
            )
        )
        assert "redmine_src = pkgs.fetchurl" in output
        assert "src = redmine_src;" in output
        assert "cp -r . $out/app/" in output  # whole tree, not selected files

    def test_exec_args_are_real_arguments(self):
        """
        They used to be repurposed as a file list, which no other template
        does and which left the exec line argument-less.
        """
        output = generate(self._spec(exec_args=["server", "-b", "0.0.0.0"]))
        assert "exec GEMSBIN/rails server -b 0.0.0.0" in output

    def test_gems_are_on_path_for_pre_exec(self):
        """`rake db:migrate` in pre-exec must resolve without a store path."""
        output = generate(self._spec(pre_exec_commands=["rake db:migrate"]))
        assert 'export PATH="GEMSBIN:$PATH"' in output
        assert "rake db:migrate" in output

    def test_writable_home_copies_and_enters_the_tree(self):
        """Rails writes inside its own tree and resolves paths from the cwd."""
        output = generate(self._spec(writable_home_at_runtime=True))
        assert 'HOME_DIR="$PWD/.redmine-home"' in output
        assert 'cp -rL --no-preserve=ownership APPDIR/. "$HOME_DIR"' in output
        assert 'cd "$HOME_DIR"' in output

    def test_no_writable_home_by_default(self):
        output = generate(self._spec())
        assert "HOME_DIR=" not in output

    def test_gemset_drives_the_dependency_set(self):
        output = generate(self._spec())
        assert "pkgs.bundlerEnv" in output
        assert "gemdir = ./.;" in output

    def test_packaged_app_installs_the_gemfile_the_gems_came_from(self):
        """
        The app runs from its own tree, so bundler resolves the tarball's
        Gemfile. If that disagrees with the lockfile the gem set was built
        from, bundler refuses to boot ("ensure_equivalent_gemfile_and_lockfile:
        Some dependencies were deleted") — so install the matching pair.
        """
        output = generate(
            self._spec(
                source=Source(url="https://x/r.tar.gz", sha256="a", archive="tar-gz")
            )
        )
        assert "cp ${./Gemfile} $out/app/Gemfile" in output
        assert "cp ${./Gemfile.lock} $out/app/Gemfile.lock" in output

    def test_local_app_keeps_its_own_gemfile(self):
        """There the recipe dir is the app, so the pair is already the same."""
        assert "cp ${./Gemfile}" not in generate(self._spec())

    def test_the_real_redmine_recipe_generates(self, catalog_recipe):
        config = tomllib.loads(
            (catalog_recipe("redmine-nixgen") / "hop3.toml").read_text()
        )
        spec = app_spec_from_config(config["nix"], config["metadata"], "redmine")
        output = generate(spec)
        assert "pkgs.ruby_3_2" in output  # redmine 5.1 needs < 3.3
        assert 'cd "$HOME_DIR"' in output  # writable home
        assert "config/database.yml" in output  # generated from PG*
        assert "rake db:migrate" in output
        assert "exec GEMSBIN/rails server" in output


class TestGoSourceExecTargetCheck:
    """
    buildGoModule names a binary after its package directory, which for a
    root main package is the last element of the *module path*. forgejo's
    `module forgejo.org` yields `bin/forgejo.org`; gitea's `code.gitea.io/gitea`
    yields `bin/gitea`. The two recipes look alike and behave differently, and
    the mismatch surfaced as a health-check timeout naming nothing useful.
    """

    def _spec(self, **kwargs):
        defaults = {
            "pname": "forgejo",
            "version": "11.0.1",
            "description": "git forge",
            "exec_target": "forgejo.org",
            "vendor_hash": "sha256-AAA=",
            "source": Source(url="https://x/src.tar.gz", sha256="x", archive="tar-gz"),
        }
        defaults.update(kwargs)
        return spec_for(GoSourcePayload, **defaults)

    def test_the_build_refuses_an_exec_target_it_did_not_produce(self):
        output = generate(self._spec())
        assert "is not a binary in" in output
        assert "ls -1 ${goApp}/bin" in output

    def test_the_check_interpolates_the_store_path(self):
        """
        `''${goApp}` is the Nix escape for a *literal* `${goApp}`, which the
        shell then reads as an unset variable and checks /bin instead.
        """
        output = generate(self._spec())
        assert "''${goApp}/bin" not in output

    def test_the_real_forgejo_recipe_execs_the_binary_go_builds(self, catalog_recipe):
        config = tomllib.loads(
            (catalog_recipe("forgejo-nixgen") / "hop3.toml").read_text()
        )
        spec = app_spec_from_config(config["nix"], config["metadata"], "forgejo")
        assert spec.exec_target == "forgejo.org"


def test_nixpkgs_wrapper_exposes_a_binding_that_does_not_move():
    """
    A recipe must be able to name the wrapped package without knowing the app id.

    The package's own let-binding is `pname` with dashes turned into
    underscores, so it renames whenever the app does. keycloak-nixgen and
    mattermost-nixgen were both made by copying a recipe and renaming the app,
    and both kept `${keycloak}` / `${mattermost}` in `extra-paths` — names that
    no longer existed. Nix failed them at BUILD time with a bare
    `undefined variable 'keycloak'`, pointing at a generated line the recipe
    author never wrote, after a 200-second deploy.
    """
    spec = AppSpec(
        pname="keycloak-nixgen",
        version="",
        description="t",
        exec_target="kc.sh",
        source=Source(url="x", sha256="x"),
        payload=NixpkgsWrapperPayload(package="keycloak"),
    )
    output = generate(spec)

    assert "keycloak_nixgen = pkgs.keycloak;" in output, "the derived binding"
    assert "pkg = keycloak_nixgen;" in output, (
        "and a stable alias, so a recipe never has to spell the derived one"
    )


def test_the_stable_binding_survives_renaming_the_app():
    """`pkg` is the point: it is the same name whatever the app is called."""
    outputs = [
        generate(
            AppSpec(
                pname=pname,
                version="",
                description="t",
                exec_target="kc.sh",
                source=Source(url="x", sha256="x"),
                payload=NixpkgsWrapperPayload(package="keycloak"),
            )
        )
        for pname in ("keycloak", "keycloak-nixgen", "keycloak-experiment-3")
    ]

    assert all("pkg = " in out for out in outputs)


def test_go_source_exposes_the_app_binary_as_pkg():
    """
    `pkg` means the same thing in every template: the application itself.

    The wrapper derivation's bin holds a generated script that execs one fixed
    subcommand, so `[admin].create` cannot use it to run `admin user create`.
    gitea-nixgen failed with `gitea: not found` while its binary sat in the
    inner derivation, one store path away and absent from the runtime PATH.
    """
    spec = AppSpec(
        pname="gitea-nixgen",
        version="1.22.6",
        description="t",
        exec_target="gitea",
        exec_args=["web"],
        source=Source(url="https://example/x.tar.gz", sha256="x", archive="tar-gz"),
        payload=GoSourcePayload(vendor_hash="sha256-x"),
    )
    output = generate(spec)

    assert "pkg = goApp;" in output, (
        "a recipe must be able to put the app's own bin on PATH via ${pkg}/bin"
    )


def test_nix_runtime_libs_reach_the_runtime_env_not_just_the_wrapper():
    """
    Anything that runs the app's own code needs its shared libraries.

    `nix-runtime-libs` became one `export LD_LIBRARY_PATH=` inside the generated
    wrapper, which covers the app process and nothing else. `[run] before-run`
    and `[admin]/[probe].create` execute directly, so they got a venv whose C
    extensions could not load: bugsink's `migrate` died with
    `ImproperlyConfigured: Error loading psycopg2 or psycopg module` while the
    identical code worked once the wrapper started it.
    """
    spec = AppSpec(
        pname="bugsink-nixgen",
        version="2.1.2",
        description="t",
        exec_target="gunicorn",
        source=Source(url="https://example/x.tar.gz", sha256="x", archive="tar-gz"),
        payload=PythonVenvPayload(
            requirements="requirements.txt", deps_hash="sha256-x"
        ),
        nix_runtime_libs=["postgresql.lib", "krb5.lib"],
    )

    assert spec.runtime_env["LD_LIBRARY_PATH"] == (
        "${pkgs.postgresql.lib}/lib:${pkgs.krb5.lib}/lib"
    ), "the libraries must be declared in the runtime env, which runtime.json carries"

    output = generate(spec)
    assert output.count("LD_LIBRARY_PATH") >= 2, (
        "both the wrapper export and the runtime env should carry it"
    )


def test_an_explicit_runtime_ld_library_path_is_not_overwritten():
    """A recipe that sets it deliberately keeps its own value."""
    spec = AppSpec(
        pname="x",
        version="1",
        description="t",
        exec_target="x",
        source=Source(url="https://example/x.tar.gz", sha256="x", archive="tar-gz"),
        payload=PythonVenvPayload(requirements="requirements.txt"),
        nix_runtime_libs=["postgresql.lib"],
        runtime_env={"LD_LIBRARY_PATH": "/hand/written"},
    )

    assert spec.runtime_env["LD_LIBRARY_PATH"] == "/hand/written"


def test_a_composer_app_shipped_as_a_zip_can_unpack_it():
    """
    buildComposerProject does its own unpack, so unzip must be in ITS inputs.

    Putting it only on the wrapping derivation — which sets `dontUnpack` — left
    nix answering `do not know how to unpack source archive`. A release zip is
    exactly what you want to package when the git tag lacks built assets, which
    is why easy-appointments needed one.
    """
    spec = AppSpec(
        pname="easy-appointments",
        version="1.5.0",
        description="t",
        exec_target="index.php",
        source=Source(url="https://example/app.zip", sha256="x", archive="zip"),
        payload=PhpAppPayload(needs_composer=True, composer_deps_hash="sha256-x"),
    )
    output = generate(spec)

    composer = output[output.index("buildComposerProject") : output.index("vendorHash")]
    assert "pkgs.unzip" in composer, "the composer build cannot unpack its own source"


def test_a_composer_app_from_a_tarball_gains_no_unzip():
    """Only add the tool when the archive actually needs it."""
    spec = AppSpec(
        pname="x",
        version="1",
        description="t",
        exec_target="index.php",
        source=Source(url="https://example/app.tar.gz", sha256="x", archive="tar-gz"),
        payload=PhpAppPayload(needs_composer=True, composer_deps_hash="sha256-x"),
    )
    output = generate(spec)

    composer = output[output.index("buildComposerProject") : output.index("vendorHash")]
    assert "unzip" not in composer


def test_python_venv_vendors_named_packages_as_source():
    """
    A package shipping per-architecture wheels must be vendored as source.

    `pip download` picks the wheel matching the build machine, so a set holding
    one puts different bytes on x86_64 than on aarch64 — and `pip-deps-hash`
    can only ever match whichever machine recorded it. That is precisely why
    bugsink, isso and radicale (the only three recipes carrying a lockfile) all
    failed on arm64 against hashes taken on x86, run after run, deterministically.

    An sdist is the same bytes everywhere, so naming those packages makes one
    recorded hash correct on every architecture — including one nobody has
    published a wheel for.
    """
    output = generate(_python_spec(source_packages=("cffi", "misaka")))

    assert "--no-binary cffi,misaka" in output


def test_python_venv_leaves_pure_python_packages_as_wheels():
    """
    Deliberately not `--no-binary :all:`.

    Forcing a pure-Python package to build from its sdist buys nothing — its
    wheel is already identical everywhere — and it breaks: html5lib's setup.py
    imports `pkg_resources`, which current setuptools no longer ships, so
    `:all:` fails the download outright.
    """
    output = generate(_python_spec())

    assert "--no-binary" not in output


def test_python_venv_downloads_exactly_the_locked_closure():
    """`--no-deps`: the lockfile IS the resolution, so this is a fetch, not a re-resolve."""
    output = generate(_python_spec(source_packages=("cffi",)))

    assert "--no-deps" in output


def test_python_venv_declares_libraries_for_compiling_sources():
    """
    Libraries land in buildInputs, not nativeBuildInputs.

    The split is what a cross-build keys off, and reaching an architecture
    without published wheels is the entire reason for compiling from source.
    """
    output = generate(_python_spec(source_packages=("cffi",), build_inputs=("libffi",)))

    assert "buildInputs = [ pkgs.libffi ];" in output
    assert "pkgs.pkg-config" in output  # build-time tool, for finding those libs


def test_python_venv_gives_the_download_step_the_same_toolchain():
    """
    Vendoring source makes the DOWNLOAD derivation compile, not just the build.

    `pip download` builds each sdist's metadata, and a PEP 517 backend
    dependency is compiled to do it — misaka's pulls in cffi, which needs
    libffi. With the libraries declared only on the app derivation, the fetch
    died on `fatal error: ffi.h: No such file or directory`, which is the last
    place anyone would look for a compiler error.
    """
    output = generate(
        _python_spec(source_packages=("misaka",), build_inputs=("libffi",))
    )
    download_phase = output[: output.index("app = pkgs.stdenv.mkDerivation")]

    assert "buildInputs = [ pkgs.libffi ];" in download_phase
    assert "pkgs.pkg-config" in download_phase


def test_python_venv_vendors_rust_crates_in_the_fetch_step():
    """
    A Rust extension's sdist build fetches crates from crates.io.

    The app build is sandboxed and offline, so that fetch cannot happen there.
    The dependency derivation — the one step allowed the network — vendors them
    instead, and the app build compiles against the vendored registry with
    cargo forbidden the network.
    """
    output = generate(_python_spec(source_packages=("bcrypt",)))

    assert "cargo vendor" in output
    assert "pkgs.cargo" in output
    assert 'replace-with = "vendored-sources"' in output
    assert "CARGO_NET_OFFLINE=true" in output


def test_python_venv_without_source_packages_needs_no_rust():
    """A wheels-only recipe must not grow a Rust toolchain it never uses."""
    output = generate(_python_spec())

    assert "pkgs.cargo" not in output


def test_python_venv_vendors_pinned_build_backends():
    """
    An offline sdist build needs its PEP 517 requirements vendored too.

    The lockfile does not carry them — it describes what the app RUNS, not what
    compiles it. radicale died on "Could not find a version that satisfies the
    requirement setuptools>=42.0.0 (from versions: none)" for exactly this
    reason; isso survived only because its runtime set happens to include
    setuptools.
    """
    output = generate(
        _python_spec(
            source_packages=("bcrypt",),
            build_requires=("setuptools==83.0.0", "setuptools-rust==1.13.0"),
        )
    )

    assert '"setuptools==83.0.0" "setuptools-rust==1.13.0"' in output


def test_python_venv_build_backends_are_fetched_without_resolution():
    """
    Pinned and --no-deps, so the closure must be listed in full.

    Resolving it would let a new release of a build tool change the vendored
    bytes and invalidate the recorded hash — a build that breaks on a day
    nobody touched the recipe.
    """
    output = generate(
        _python_spec(
            source_packages=("bcrypt",), build_requires=("setuptools==83.0.0",)
        )
    )

    assert (
        'pip download --no-deps --no-binary bcrypt --dest $out "setuptools==' in output
    )


def test_python_venv_build_backends_obey_the_source_only_declaration():
    """
    A package named source-only must arrive as source in BOTH fetches.

    The build-backend fetch is a second `pip download`, and without the flag it
    quietly took a wheel for a package the recipe had declared source-only —
    re-introducing the per-architecture bytes the declaration exists to remove,
    with nothing in the output saying so.
    """
    output = generate(
        _python_spec(source_packages=("maturin",), build_requires=("maturin==1.14.1",))
    )

    assert 'pip download --no-deps --no-binary maturin --dest $out "maturin==' in output


def test_python_venv_pip_belongs_to_the_apps_interpreter():
    """
    `pkgs.python3Packages.pip` is the *default* interpreter's pip, not the app's.

    A recipe that pins `runtime-package` (bugsink pins python312 so a newer
    nixpkgs does not migrate it to 3.13) then downloads wheels tagged for the
    nixpkgs default, and the offline install fails to find a compatible
    distribution for a package it has just vendored.
    """
    output = generate(_python_spec(runtime_package="python312"))

    assert "python = pkgs.python312;" in output
    assert "python.pkgs.pip" in output
    assert "python3Packages.pip" not in output


def test_python_venv_gives_cargo_a_writable_home():
    """
    The sandbox points HOME at /homeless-shelter, which is not writable.

    cargo stages its downloads under CARGO_HOME, so with the default it fails
    with `Permission denied` on `/homeless-shelter/.cargo/registry/...` — a path
    the recipe never mentions.
    """
    output = generate(_python_spec(source_packages=("bcrypt",)))
    fetch_phase = output[: output.index("app = pkgs.stdenv.mkDerivation")]

    assert "export CARGO_HOME=$TMPDIR/cargo-fetch" in fetch_phase
    # Before the fetch, not merely somewhere in the phase: a build backend
    # written in Rust (maturin) compiles during `pip download` and needs a
    # writable home earlier than the vendor step does.
    assert fetch_phase.index("export CARGO_HOME") < fetch_phase.index(
        "pip download --require-hashes"
    )


def test_python_venv_does_not_fix_up_the_vendored_set():
    """
    stdenv's fixupPhase must not touch downloaded dependencies.

    `patchShebangs` rewrites `#!/bin/bash` to a store path and reaches inside
    vendored crates (autocfg's test script, wasi's CI scripts). That breaks the
    derivation three ways: a fixed-output derivation may not reference store
    paths; the reference is machine-specific, which is the very non-determinism
    this vendoring removes; and editing a crate's files invalidates the
    .cargo-checksum.json that cargo verifies when building offline.
    """
    output = generate(_python_spec(source_packages=("bcrypt",)))
    fetch_phase = output[: output.index("app = pkgs.stdenv.mkDerivation")]

    assert "dontFixup = true;" in fetch_phase


def test_python_venv_caps_lints_on_vendored_crates():
    """
    Third-party Rust must not fail the build over a lint we cannot fix.

    cargo applies `--cap-lints allow` to crates from a registry for exactly
    that reason, but not to workspace paths — and every crate vendored out of a
    Python sdist arrives as a path. Without the cap, a rustc that promotes a
    lint to deny-by-default breaks an app nobody edited: symbolic 8.7.2 stops
    compiling at 1.87 on `dangerous_implicit_autorefs`.
    """
    output = generate(_python_spec(source_packages=("bcrypt",)))
    app_phase = output[output.index("app = pkgs.stdenv.mkDerivation") :]

    assert 'rustflags = ["--cap-lints", "allow"]' in app_phase


def test_python_venv_cargo_config_is_written_literally():
    """
    The cargo config heredoc must not be expanded by the shell.

    Its body is TOML with prose in it, and prose contains backticks. Unquoted,
    the shell reads them as a command substitution and runs them mid-build:

        1774: dangerous_implicit_autorefs: command not found

    The written file is then quietly not what the template says it is.
    """
    output = generate(_python_spec(source_packages=("bcrypt",)))

    assert "cat > $CARGO_HOME/config.toml << 'CARGOCFG'" in output


def test_go_source_pnpm_fetcher_version_is_emitted_when_set():
    """
    nixpkgs' reproducibility knob reaches the generated fetchDeps call.

    Without it the fetcher leaves file permissions as pnpm happened to create
    them, so the same lockfile produces different bytes on different machines:
    vikunja installed from the published catalog hit a hash mismatch against a
    hash that reproduced perfectly on the machine that recorded it.
    """
    output = generate(
        _go_spec(
            frontend_pnpm=True,
            frontend_build="pnpm run build",
            frontend_output="dist",
            pnpm_deps_hash="sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            pnpm_fetcher_version=3,
        )
    )

    assert "fetcherVersion = 3;" in output


def test_go_source_omits_pnpm_fetcher_version_by_default():
    """
    The default nixpkgs pin's fetcher rejects the argument outright.

    Emitting it unconditionally would break every pnpm recipe that has not also
    pinned a newer nixpkgs, so it appears only when a recipe asks for it.
    """
    output = generate(
        _go_spec(
            frontend_pnpm=True,
            frontend_build="pnpm run build",
            frontend_output="dist",
            pnpm_deps_hash="sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        )
    )

    assert "fetcherVersion" not in output


def test_php_builtin_server_gets_workers():
    """
    A Nix-built PHP app needs the concurrency setting declared, not detected.

    PHP's built-in server handles one request at a time, so an app that fetches
    its own URL deadlocks. The platform sets `PHP_CLI_SERVER_WORKERS` by
    matching `php -S` in the worker command, and a Nix app's command is an
    opaque store path — invoice-ninja-nix bound its port and never answered.
    """
    output = generate(_composer_spec(serve_mode="builtin"))

    assert "PHP_CLI_SERVER_WORKERS" in output


def test_php_artisan_serve_gets_workers_too():
    """`artisan serve` is the same single-threaded server behind a wrapper."""
    output = generate(_composer_spec(serve_mode="artisan"))

    assert "PHP_CLI_SERVER_WORKERS" in output


def test_a_php_app_behind_a_real_server_gets_no_workers_setting():
    """Only PHP's own server has the defect; nothing else is touched."""
    output = generate(_composer_spec(serve_mode="custom", exec_target="frankenphp"))

    assert "PHP_CLI_SERVER_WORKERS" not in output


def test_an_explicit_worker_count_wins():
    """The template supplies a default; it does not override the recipe."""
    output = generate(
        _composer_spec(
            serve_mode="builtin", runtime_env={"PHP_CLI_SERVER_WORKERS": "2"}
        )
    )

    assert '"PHP_CLI_SERVER_WORKERS": "2"' in output
