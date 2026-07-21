# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM102

"""Data types describing a template specification for an app.

A spec captures all the app-specific information needed to generate a
``hop3.nix`` expression. Templates consume specs and emit Nix strings.

The spec format is currently Python dataclasses. In the real
implementation, these will be parsed from a ``[nix]`` section in
``hop3.toml``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    """A source archive or binary to fetch via ``pkgs.fetchurl``.

    The ``archive`` field describes what kind of archive (if any) needs
    to be unpacked. Templates use it to generate the correct unpackPhase.

    Archive types:
        None       — single file (binary, .php, .war, etc.), no unpack
        "tar-gz"   — .tar.gz / .tgz
        "tar-bz2"  — .tar.bz2 / .tbz2
        "tar-xz"   — .tar.xz
        "zip"      — .zip (needs unzip in nativeBuildInputs)
    """

    url: str
    sha256: str
    executable: bool = False  # True for single-binary downloads
    archive: str | None = None  # None, "tar-gz", "tar-bz2", "tar-xz", "zip"

    def as_nix(self, binding_name: str) -> str:
        """Emit the Nix ``let`` binding for this source."""
        extra_lines = []
        if self.executable:
            extra_lines.append("    executable = true;")
        joined = "\n".join(extra_lines)
        body = f"""    url = "{self.url}";
    sha256 = "{self.sha256}";"""
        if joined:
            body += "\n" + joined
        return f"  {binding_name} = pkgs.fetchurl {{\n{body}\n  }};"

    @property
    def needs_unzip(self) -> bool:
        return self.archive == "zip"

    @property
    def is_archive(self) -> bool:
        return self.archive is not None

    def unpack_command(self, strip_components: int = 1) -> str:
        """Return the shell command to unpack this archive."""
        if self.archive == "tar-gz":
            return f"tar xzf $src --strip-components={strip_components}"
        if self.archive == "tar-bz2":
            return f"tar xjf $src --strip-components={strip_components}"
        if self.archive == "tar-xz":
            return f"tar xJf $src --strip-components={strip_components}"
        if self.archive == "zip":
            return "unzip -q $src"  # zip has no strip-components
        raise ValueError(f"Cannot unpack archive type: {self.archive!r}")


@dataclass(frozen=True)
class FileMapping:
    """Copy instruction from the unpacked source to the output.

    Used by prebuilt-archive template. ``source`` is relative to the
    archive root (after unpack); ``destination`` is relative to ``$out``.

    If ``source`` ends in ``/*``, all files in that directory are copied
    into ``destination``. Otherwise, the single file or directory is
    copied as-is.
    """

    source: str  # Path in the unpacked archive, e.g., "bin/mattermost"
    destination: str  # Path under $out, e.g., "bin/"
    recursive: bool = True  # Use `cp -r`
    executable: bool = False  # chmod +x after copy


@dataclass(frozen=True)
class ConditionalEnvVar:
    """An env export that's only set if the given var is empty at runtime.

    Example: set ``DATABASE_URL`` from PG* vars only if not already set.
    """

    name: str
    condition_var: str  # Set `name` only if this var is empty
    value: str


@dataclass(frozen=True)
class ConfigFile:
    """A config file to generate in the wrapper script at startup.

    Uses an unquoted shell heredoc, so ``${VAR}`` and ``$(cmd)`` are
    expanded at runtime.

    Formats:
        - ``ini``: ``sections`` is a dict of section name -> dict of key -> value
        - ``raw``: ``raw_content`` is used directly
        - ``yaml``, ``json``, ``env``: planned
    """

    path: str  # e.g., "custom/conf/app.ini"
    format: str  # "ini", "raw", "yaml", "json", "env"
    sections: dict[str, dict[str, str]] | None = None
    raw_content: str | None = None
    # Only generate the file if it doesn't already exist
    create_if_missing: bool = False


@dataclass(frozen=True)
class AppSpec:
    """Complete template specification for a single app.

    Fields map onto the common pattern observed across 22 hand-written
    hop3.nix files in apps/real-apps-nix/.
    """

    pname: str
    version: str
    description: str
    template: str  # Template name, e.g., "prebuilt-binary"
    source: Source

    # --- prebuilt-binary fields ---
    binary_name: str | None = None

    # --- prebuilt-archive fields ---
    source_root: str | None = None  # The directory inside the archive
    file_mappings: list[FileMapping] = field(default_factory=list)

    # --- php-app fields ---
    # PHP package attribute name in nixpkgs, e.g., "php82", "php83"
    php_version: str = "php82"
    # PHP extensions to enable (from the `all` set in withExtensions)
    php_extensions: list[str] = field(default_factory=list)
    # Whether the app needs `composer install` in the build phase
    needs_composer: bool = False
    # For php-app: sha256 of the vendored composer dependency set (the FOD
    # that fetches from composer.lock). Analogous to pip_deps_hash.
    composer_deps_hash: str | None = None
    # For php-app: composer runs a strict `composer validate` by default.
    # Third-party releases frequently fail it for benign reasons (the app
    # still installs); set false to skip, explicitly, per app.
    composer_strict_validation: bool = True
    # Extra flags to pass to composer install (e.g., "--ignore-platform-reqs")
    composer_extra_flags: list[str] = field(default_factory=list)
    # Number of leading path components to strip when extracting tarball
    strip_components: int = 1
    # Serving mode: "builtin" (php -S), "artisan" (php artisan serve), "custom"
    serve_mode: str = "builtin"
    # Web document root, relative to $out/app. Used by php -S -t <root>.
    # Example: "htdocs" for Dolibarr, "" for most apps.
    web_root: str = ""
    # Directories to create under $out/app after copying source (e.g., "storage")
    post_install_dirs: list[str] = field(default_factory=list)
    # Treat source as a single file (like adminer.php), not a tarball
    single_file: bool = False
    # If True, app doesn't need `cp -r . $out/app/` (e.g., single file case)
    skip_source_copy: bool = False
    # If True, wrapper creates symlinks from Nix store to writable cwd before
    # serving. Required for apps that need runtime-generated config files
    # (Laravel .env, Nextcloud config.php, etc.) since the Nix store is read-only.
    needs_writable_dir: bool = False
    # Extra nativeBuildInputs (beyond php and composer). Strings are taken
    # as-is and placed into the Nix attrset, so use full attr paths like
    # "pkgs.nodejs" or "pkgs.unzip".
    extra_native_build_inputs: list[str] = field(default_factory=list)

    # --- nixpkgs-wrapper fields ---
    # Name of the nixpkgs attribute to wrap, e.g., "radicale" for pkgs.radicale
    nixpkgs_package: str | None = None
    # Free-form shell appended to the installPhase, after the wrapper is
    # emitted but before runtime.json. Use this to bake artefacts into
    # $out at package time — e.g., copying a nixpkgs package into a
    # writable $out/<pname>-home and running its build command there so
    # runtime can exec it with --optimized from a read-only store path.
    # Content is emitted **raw** (no nix_escape), so `${pkgs.X}` and
    # Nix let-bindings interpolate at build time.
    install_extra: str | None = None
    # Overrides the PKGBIN substitution in the wrapper's exec line. If
    # set, the exec line becomes `<exec-prefix>/<exec-target>` instead
    # of `${<binding>}/bin/<exec-target>`. Useful together with
    # install-extra when the runnable sits under a dir populated by
    # install-extra (e.g., "$out/keycloak-home/bin" for Keycloak).
    exec_prefix: str | None = None
    # Override arguments passed to `pkgs.<name>.override { ... }`. Each
    # value is emitted **raw** into the Nix let-block (no nix_escape),
    # so it can reference `pkgs`, `writeText`, etc. Use for nixpkgs
    # packages that accept build-time config (e.g., Keycloak's
    # `confFile = pkgs.writeText "kc.conf" "db=postgres\n"` bakes the
    # postgres-DB profile inside nixpkgs' own buildPhase, sidestepping
    # the runtime `kc.sh build` writable-FS problem).
    nixpkgs_overrides: dict[str, str] = field(default_factory=dict)
    # When True, the wrapper lazy-copies the nixpkgs package tree into
    # $PWD/.<pname>-home at first launch (cp -rL + chmod u+w), then
    # execs the runnable out of the writable copy. Solves the
    # "nixpkgs ships read-only, app writes inside the install dir"
    # class of apps — Keycloak (Quarkus augmentation), Jenkins
    # (plugin install), Mattermost-nixpkgs, etc. Copy happens once per
    # app instance (marked with $HOME_DIR/.hop3-ready); subsequent
    # restarts reuse the existing copy.
    writable_home_at_runtime: bool = False
    # Optional env var exported by the wrapper, pointing at the
    # writable home (e.g., "KC_HOME_DIR" for Keycloak). Only consulted
    # when `writable_home_at_runtime` is True.
    writable_home_env_var: str | None = None
    # Per-app nixpkgs pin override. Absent → the generator's default pin (see
    # templates/base.py NIXPKGS_REV). Set BOTH together when an app needs a
    # package the default pin predates (e.g. etherpad-lite, added in nixos-25.05
    # while the default is nixos-24.11). Only honoured by the nixpkgs-wrapper
    # template; toml_adapter rejects it on other templates (no silent-ignore).
    nixpkgs_rev: str | None = None
    nixpkgs_sha256: str | None = None
    # Internal: raw shell emitted at the top of the wrapper (after
    # shebang, before local vars). Populated by templates; NOT mapped
    # from hop3.toml directly. Emitted without nix_escape so
    # `${binding}` references interpolate at Nix build time.
    runtime_prelude: str | None = None
    # Extra let-bindings added to the generated Nix expression's let-
    # block (e.g., `jdk = "pkgs.zulu21"` → `jdk = pkgs.zulu21;`).
    # Values are raw Nix expressions (not nix_escape'd). Used together
    # with `env_exports_raw` / `extra_paths` to reference packages
    # other than the primary `nixpkgs_package` — e.g., Keycloak's
    # `.kc.sh-wrapped` needs JAVA_HOME pointing at a nixpkgs JDK.
    let_extra: dict[str, str] = field(default_factory=dict)
    # Env vars exported in the wrapper with raw values that Nix
    # interpolates at build time (unlike `env_exports`, which goes
    # through nix_escape). Use when the value must reference a
    # let-binding (e.g., `JAVA_HOME = "${jdk}"`).
    env_exports_raw: dict[str, str] = field(default_factory=dict)

    # --- node-prebuilt / java-war / python-venv fields ---
    # Nix package attribute for the runtime, e.g., "nodejs_22", "jdk17", "python3"
    runtime_package: str | None = None
    # For node-prebuilt: unpack the tarball without a top-level dir?
    unpack_without_top_level: bool = False
    # For java-war: relative path to the WAR file under $out/app
    war_file: str | None = None
    # For java-war: extra JVM args (go in JAVA_OPTS)
    jvm_default_opts: str | None = None
    # For python-venv: packages to pip install.
    # DEPRECATED as a sole source of truth — bare names are unpinned and
    # unhashed, so the build is neither reproducible nor offline-capable.
    # Ship a hash-pinned lockfile (`pip_requirements`) instead.
    pip_packages: list[str] = field(default_factory=list)
    # For python-venv: hash-pinned lockfile, relative to the app directory.
    # Generate with `uv export --format requirements-txt` or
    # `pip-compile --generate-hashes`; every entry needs a `--hash=sha256:...`.
    pip_requirements: str | None = None
    # For node-pnpm-install: committed manifest + lockfile, relative to the
    # app directory. A synthesized manifest cannot be locked, so the
    # dependency set must be recorded in the recipe.
    node_manifest: str | None = None
    node_lockfile: str | None = None
    # sha256 of the fetched pnpm store (fixed-output derivation).
    node_deps_hash: str | None = None
    # For node-pnpm-install: which nixpkgs pnpm to build with. The committed
    # lockfile's format must be one this major can read (see
    # PNPM_LOCKFILE_VERSIONS in templates/node_pnpm_install.py).
    node_pnpm_package: str = "pnpm_9"
    # For go-source: sha256 of the vendored Go module set. `go.sum` already
    # hashes every module; this pins the resolved set as a whole.
    go_vendor_hash: str | None = None
    # For go-source: which command packages to build (default: all).
    go_sub_packages: list[str] = field(default_factory=list)
    # For go-source: linker flags, e.g. version stamping.
    go_ldflags: list[str] = field(default_factory=list)
    # For python-venv: sha256 of the vendored-wheels fixed-output derivation
    # (the analogue of buildGoModule's `vendorHash`). Obtain it by building
    # once with a placeholder and reading the `got:` line Nix prints.
    pip_deps_hash: str | None = None

    # --- wrapper script fields (used by all templates) ---
    exec_target: str | None = None  # What to exec (relative to $out/bin)
    exec_args: list[str] = field(default_factory=list)

    # Local shell variables at top of wrapper (not exported)
    local_vars: dict[str, str] = field(default_factory=dict)
    # Static env var exports
    env_exports: dict[str, str] = field(default_factory=dict)
    # Conditional env var exports
    conditional_env_exports: list[ConditionalEnvVar] = field(default_factory=list)
    # Shell commands to run before exec (e.g., "mkdir -p data")
    pre_exec_commands: list[str] = field(default_factory=list)
    # Config files to generate at startup
    config_files: list[ConfigFile] = field(default_factory=list)

    # --- runtime metadata fields ---
    # Runtime env (goes into hop3.runtime.json and top-level `env` attr)
    runtime_env: dict[str, str] = field(default_factory=dict)
    # Additional path entries (beyond $out/bin). Can reference Nix let-bindings
    # like "${php}/bin" — they will be interpolated by Nix at build time.
    extra_paths: list[str] = field(default_factory=list)

    # nixpkgs attribute paths (e.g. "postgresql.lib", "krb5.lib",
    # "stdenv.cc.cc.lib") whose ``/lib`` directories are emitted into the
    # wrapper's ``LD_LIBRARY_PATH`` export with **raw Nix interpolation**
    # (not nix_escape). Fixes the "pip-installed C extensions can't find
    # their transitive shared libs under a Nix-built Python venv" class
    # (libpq.so.5, libkrb5, libstdc++.so.6, etc.).
    nix_runtime_libs: list[str] = field(default_factory=list)
