# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, f-string-in-exception]

"""
Data types describing a template specification for an app.

A spec captures the app-specific information needed to generate a ``hop3.nix``
expression. Templates consume specs and emit Nix strings; ``toml_adapter``
builds them from the ``[nix]`` section of ``hop3.toml``.

A spec has two halves. :class:`AppSpec` holds what *every* template needs —
identity, source, the wrapper script, runtime metadata — and a **payload**
holding what exactly one template needs. The payload is the discriminator:
its type determines which template renders the spec, so there is no separate
template-name field to disagree with it.

The split is not cosmetic. A single flat spec made every template's fields
visible to every other template, which meant nothing could distinguish a field
an app had not set from one the chosen template would never read; a mistyped or
misplaced key was silently dropped, and one field was quietly reinterpreted to
mean two different things depending on who read it. With payloads, a key that
belongs to another template has nowhere to go, and the adapter rejects it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, TypeVar


@dataclass(frozen=True)
class Source:
    """
    A source archive or binary to fetch via ``pkgs.fetchurl``.

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
    """
    Copy instruction from the unpacked source to the output.

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
    """
    An env export that's only set if the given var is empty at runtime.

    Example: set ``DATABASE_URL`` from PG* vars only if not already set.
    """

    name: str
    condition_var: str  # Set `name` only if this var is empty
    value: str


@dataclass(frozen=True)
class ConfigFile:
    """
    A config file to generate in the wrapper script at startup.

    Uses an unquoted shell heredoc, so ``${VAR}`` and ``$(cmd)`` are
    expanded at runtime.

    Formats:
        - ``ini``: ``sections`` is a dict of section name -> dict of key -> value
        - ``raw``: ``raw_content`` is used directly — this is how JSON, YAML and
          anything else without a dedicated formatter is expressed
    """

    path: str  # e.g., "custom/conf/app.ini"
    format: str  # "ini" or "raw"
    sections: dict[str, dict[str, str]] | None = None
    raw_content: str | None = None
    # Only generate the file if it doesn't already exist
    create_if_missing: bool = False


# ---------------------------------------------------------------------------
# Per-template payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemplatePayload:
    """
    Base for the per-template half of a spec.

    ``template_name`` is the discriminator: it names the template that renders
    a spec carrying this payload, and is what the registry dispatches on.
    """

    template_name: ClassVar[str]


@dataclass(frozen=True)
class PrebuiltBinaryPayload(TemplatePayload):
    template_name: ClassVar[str] = "prebuilt-binary"

    # Name the fetched binary is installed as under $out/bin (default: pname).
    binary_name: str | None = None


@dataclass(frozen=True)
class PrebuiltArchivePayload(TemplatePayload):
    template_name: ClassVar[str] = "prebuilt-archive"

    # What to copy out of the unpacked archive into $out.
    file_mappings: list[FileMapping] = field(default_factory=list)


@dataclass(frozen=True)
class NodePrebuiltPayload(TemplatePayload):
    template_name: ClassVar[str] = "node-prebuilt"

    # Some npm tarballs have no top-level directory to strip.
    unpack_without_top_level: bool = False


@dataclass(frozen=True)
class JavaWarPayload(TemplatePayload):
    template_name: ClassVar[str] = "java-war"

    war_file: str | None = None  # Path to the WAR under $out/app
    jvm_default_opts: str | None = None  # Extra JVM args, via $JAVA_OPTS


@dataclass(frozen=True)
class RubyBundlerPayload(TemplatePayload):
    """
    ruby-bundler needs nothing beyond the shared core.

    The gem set comes from the committed ``Gemfile`` / ``Gemfile.lock`` /
    ``gemset.nix`` triple next to the recipe, which the template references by
    relative path rather than through a spec field.
    """

    template_name: ClassVar[str] = "ruby-bundler"


@dataclass(frozen=True)
class PythonVenvPayload(TemplatePayload):
    template_name: ClassVar[str] = "python-venv"

    # Hash-pinned lockfile relative to the app directory. Generate with
    # `uv export --format requirements-txt` or `pip-compile --generate-hashes`;
    # every entry needs a `--hash=sha256:...`.
    requirements: str | None = None
    # sha256 of the vendored-wheels fixed-output derivation (the analogue of
    # buildGoModule's `vendorHash`). Build once with a placeholder and read the
    # `got:` line Nix prints.
    deps_hash: str | None = None
    # Packages that must be vendored as SOURCE rather than as a wheel.
    #
    # `pip download` resolves for the host platform, so any package shipping
    # per-architecture wheels puts different bytes in the vendored set on
    # different machines and `deps_hash` can only ever match one of them. That
    # is why bugsink, isso and radicale — the only three recipes carrying a
    # lockfile — all failed on arm64 while their hashes were recorded on x86.
    #
    # Naming them here makes the vendored set architecture-independent: one
    # hash is then correct everywhere, including on a platform nobody has
    # published a wheel for. Applies to the packages with compiled extensions,
    # NOT to everything: forcing a pure-Python package to build from its sdist
    # buys nothing and breaks (html5lib's setup.py imports `pkg_resources`,
    # which current setuptools no longer provides).
    source_packages: tuple[str, ...] = ()
    # nixpkgs attributes needed to compile those sources, e.g. ("libffi",).
    # Declared per recipe because it is a property of the dependency set, and
    # a missing one is a named linker error rather than a mystery.
    build_inputs: tuple[str, ...] = ()
    # PEP 517 build backends, pinned, vendored alongside the runtime set.
    #
    # Building a source distribution offline needs its build requirements to be
    # present too, and those are not in the lockfile — a lockfile describes what
    # the app RUNS, not what compiles it. isso only worked without this because
    # its runtime set happens to include setuptools and wheel; radicale's does
    # not, and its build died on "Could not find a version that satisfies the
    # requirement setuptools>=42.0.0 (from versions: none)".
    #
    # Every entry is pinned and fetched with --no-deps, so the closure has to be
    # listed in full. That is deliberate: resolving it would let a new release of
    # a build tool change the vendored bytes, and the hash with them. A missing
    # entry fails loudly, naming the package pip could not find.
    build_requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodePnpmInstallPayload(TemplatePayload):
    template_name: ClassVar[str] = "node-pnpm-install"

    # The npm package to install (e.g. "directus@11.17.2").
    npm_package: str | None = None
    # Committed manifest + lockfile, relative to the app directory. A
    # synthesized manifest cannot be locked, so the dependency set has to be
    # recorded in the recipe.
    manifest: str | None = None
    lockfile: str | None = None
    # sha256 of the fetched pnpm store (fixed-output derivation).
    deps_hash: str | None = None
    # Which nixpkgs pnpm to build with. The committed lockfile's format must be
    # one this major can read (see PNPM_LOCKFILE_VERSIONS in the template).
    pnpm_package: str = "pnpm_9"
    # npm packages with node-gyp native addons to compile from source, offline,
    # in the sandbox (e.g. ["isolated-vm"]). The default `--ignore-scripts`
    # install skips their build; each name here is then `pnpm rebuild`-ed with
    # the C/C++ toolchain and the pinned Node headers. A prebuilt `.node`
    # shipped inside an npm package needs no entry.
    native_packages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JavaGradlePayload(TemplatePayload):
    template_name: ClassVar[str] = "java-gradle"

    # Committed dependency lockfile in nixpkgs' Gradle `mitmCache`/`fetchDeps`
    # format — the buildGoModule.vendorHash analogue for Gradle.
    deps_json: str = "deps.json"
    # Applied to the source before the build (e.g. a build-timestamp strip).
    patches: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    # The produced jar (glob) and the name it is installed as.
    jar_glob: str | None = None
    jar_name: str | None = None


@dataclass(frozen=True)
class NixpkgsWrapperPayload(TemplatePayload):
    template_name: ClassVar[str] = "nixpkgs-wrapper"

    # The nixpkgs attribute to wrap, e.g. "radicale" for pkgs.radicale.
    package: str | None = None
    # Free-form shell appended to the installPhase, after the wrapper is emitted
    # but before runtime.json. Bakes artefacts into $out at package time — e.g.
    # copying a nixpkgs package into a writable $out/<pname>-home and running
    # its build command there. Emitted **raw** (no nix_escape), so `${pkgs.X}`
    # and let-bindings interpolate at build time.
    install_extra: str | None = None
    # Overrides the PKGBIN substitution in the wrapper's exec line: the exec
    # line becomes `<exec_prefix>/<exec_target>`. Used with `install_extra` when
    # the runnable sits under a directory that `install_extra` populated.
    exec_prefix: str | None = None
    # Arguments passed to `pkgs.<name>.override { ... }`. Values are emitted
    # **raw** into the let-block, so they can reference `pkgs`, `writeText` etc.
    # For nixpkgs packages accepting build-time config — e.g. Keycloak's
    # `confFile` bakes the postgres profile inside nixpkgs' own buildPhase.
    overrides: dict[str, str] = field(default_factory=dict)
    # Extra let-bindings in the generated expression (e.g. `jdk = "pkgs.zulu21"`
    # → `jdk = pkgs.zulu21;`). Raw Nix expressions, not nix_escape'd. Used with
    # `env_exports_raw` / `extra_paths` to reference packages other than
    # `package` — e.g. a wrapped `kc.sh` needing JAVA_HOME on a nixpkgs JDK.
    let_extra: dict[str, str] = field(default_factory=dict)
    # Env vars exported in the wrapper with values Nix interpolates at build
    # time (unlike `env_exports`, which goes through nix_escape). Use when the
    # value must reference a let-binding (e.g. `JAVA_HOME = "${jdk}"`).
    env_exports_raw: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PhpAppPayload(TemplatePayload):
    template_name: ClassVar[str] = "php-app"

    # PHP package attribute in nixpkgs, e.g. "php82", "php83".
    php_version: str = "php82"
    # Extensions to enable (from the `all` set in withExtensions).
    php_extensions: list[str] = field(default_factory=list)
    # Whether the app needs `composer install` in the build phase.
    needs_composer: bool = False
    # sha256 of the vendored composer dependency set (the FOD that fetches from
    # composer.lock).
    composer_deps_hash: str | None = None
    # Composer runs a strict `composer validate` by default. Third-party
    # releases frequently fail it for benign reasons (the app still installs);
    # set false to skip it, explicitly, per app.
    composer_strict_validation: bool = True
    # Extra flags for composer install (e.g. "--ignore-platform-reqs").
    composer_extra_flags: list[str] = field(default_factory=list)
    # Serving mode: "builtin" (php -S), "artisan" (php artisan serve), "custom".
    serve_mode: str = "builtin"
    # Web document root relative to $out/app, for `php -S -t <root>`.
    # E.g. "htdocs" for Dolibarr, "" for most apps.
    web_root: str = ""
    # Directories to create under $out/app after copying source (e.g. "storage").
    post_install_dirs: list[str] = field(default_factory=list)
    # Treat source as a single file (like adminer.php), not a tarball.
    single_file: bool = False
    # Skip `cp -r . $out/app/` (e.g. the single-file case).
    skip_source_copy: bool = False
    # Wrapper symlinks store paths into a writable cwd before serving.
    # Required for apps needing runtime-generated config files (Laravel .env,
    # Nextcloud config.php) since the store is read-only. Distinct from the
    # core `writable_home_at_runtime`, which copies a whole tree once.
    needs_writable_dir: bool = False
    # Extra nativeBuildInputs beyond php and composer. Taken as-is into the Nix
    # attrset, so use full attribute paths like "pkgs.nodejs".
    extra_native_build_inputs: list[str] = field(default_factory=list)
    # Recipe-local files to ship into $out/app (paths relative to the recipe
    # dir, copied to the same path under $out/app). For an app whose headless
    # installer needs a script that is NOT in the upstream tarball — e.g.
    # WordPress has no bundled CLI, so it ships its own wp-install.php that calls
    # core wp_install(). Lets the nix recipe REUSE a reviewable script file
    # instead of re-encoding install logic inline. The path `${./<f>}` resolves
    # against the generated hop3.nix's own directory (the recipe dir), so Nix
    # imports each file from there at build time.
    install_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GoSourcePayload(TemplatePayload):
    template_name: ClassVar[str] = "go-source"

    # sha256 of the vendored Go module set. `go.sum` already hashes every
    # module; this pins the resolved set as a whole.
    vendor_hash: str | None = None
    # Which command packages to build (default: all).
    sub_packages: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)
    # Vendor via the Go module proxy (`go mod download`) instead of
    # `go mod vendor`. Needed by projects whose go.mod trips the vendored
    # `vendor/modules.txt` explicit-marking consistency check (e.g. gitea).
    proxy_vendor: bool = False
    # Override the Go toolchain buildGoModule compiles with (a nixpkgs attr like
    # "go_1_24"). Building from source ties the app to the pinned nixpkgs' Go;
    # an app whose go.mod wants a newer Go sets this to the newest the pin still
    # ships (GOTOOLCHAIN=local forbids a network download).
    go_version: str | None = None
    # Extra directories copied from the SOURCE tree into the static root
    # alongside the built frontend. gitea/forgejo resolve both `public/` and
    # `options/` (locales, gitignores, licences) under StaticRootPath; without
    # the latter gitea crash-loops at boot on a missing translation. These are
    # source assets, not build outputs.
    static_dirs: list[str] = field(default_factory=list)
    # A JS frontend (gitea/forgejo/vikunja) is built in a separate derivation
    # and exposed to the wrapper as $HOP3_GO_FRONTEND. `frontend_build` is the
    # (offline) build command; `npm_deps_hash` pins the npm dependency set (the
    # buildGoModule.vendorHash analogue for npm); `frontend_output` is the
    # built-assets directory copied to the derivation output.
    frontend_build: str | None = None
    npm_deps_hash: str | None = None
    frontend_output: str = "public"
    frontend_source_root: str | None = None
    # Frontend built with pnpm (vikunja) instead of npm (gitea): uses
    # pnpm.fetchDeps + the pnpm configHook rather than buildNpmPackage.
    frontend_pnpm: bool = False
    pnpm_deps_hash: str | None = None
    pnpm_package: str = "pnpm_9"
    frontend_node_package: str = "nodejs"
    # Embed the built frontend into the source at this path before the Go build
    # (apps that `//go:embed` the assets, e.g. vikunja's `frontend/dist`),
    # instead of the default disk-served wiring ($HOP3_GO_FRONTEND).
    frontend_embed_path: str | None = None


P = TypeVar("P", bound=TemplatePayload)


@dataclass(frozen=True)
class AppSpec:
    """
    Complete template specification for a single app.

    The fields here are the ones *every* template may read. Anything specific to
    one template lives in :attr:`payload`.
    """

    pname: str
    version: str
    description: str
    source: Source
    payload: TemplatePayload

    # --- source extraction (any template fetching an archive) ---
    # The directory inside the archive that holds the app.
    source_root: str | None = None
    # Leading path components to strip when extracting.
    strip_components: int = 1

    # --- runtime ---
    # Nix package attribute for the runtime, e.g. "nodejs_22", "jdk17".
    runtime_package: str | None = None

    # --- per-app nixpkgs pin ---
    # Absent → the generator's default pin (see templates/base.py NIXPKGS_REV).
    # Set BOTH together when an app needs a package the default pin predates
    # (e.g. etherpad-lite, in nixos-25.05 while the default is nixos-24.11).
    # Only some templates honour it; toml_adapter rejects it on the others
    # rather than silently ignoring it.
    nixpkgs_rev: str | None = None
    nixpkgs_sha256: str | None = None

    # --- wrapper script (used by all templates) ---
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
    # When True, the wrapper lazy-copies the package tree into a writable home
    # at first launch (cp -rL + chmod u+w), then execs out of the copy. Solves
    # the "ships read-only, app writes inside its own install dir" class —
    # Keycloak (Quarkus augmentation), Rails apps writing tmp/ and log/. The
    # copy happens once per app instance (marked with $HOME_DIR/.hop3-ready).
    writable_home_at_runtime: bool = False
    # Optional env var exported by the wrapper, pointing at the writable home
    # (e.g. "KC_HOME_DIR"). Only consulted when writable_home_at_runtime.
    writable_home_env_var: str | None = None
    # Internal: raw shell emitted at the top of the wrapper (after shebang,
    # before local vars). Populated by templates; NOT mapped from hop3.toml.
    # Emitted without nix_escape so `${binding}` references interpolate at
    # Nix build time.
    runtime_prelude: str | None = None

    # --- runtime metadata ---
    # Runtime env (goes into hop3/runtime.json and the top-level `env` attr)
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

    def __post_init__(self) -> None:
        """
        Put ``LD_LIBRARY_PATH`` in the RUNTIME env, not only in the wrapper.

        ``nix_runtime_libs`` used to become a single ``export`` line inside the
        generated wrapper script. That covers the app itself and nothing else —
        and Hop3 runs an app's own code in two other places: ``[run] before-run``
        and the ``[admin]``/``[probe]`` create commands, both of which execute
        directly, not through the wrapper.

        bugsink showed what that costs. Its bootstrap is a Django ``migrate``,
        and psycopg loads ``libpq.so.5`` dynamically, so the script died with
        ``ImproperlyConfigured: Error loading psycopg2 or psycopg module`` while
        the very same code worked once the wrapper started it. Declaring the
        libraries in the runtime env puts them in ``runtime.json``, which
        ``make_env()`` applies — so every path that runs the app's code sees
        them, which is what the recipe was asking for in the first place.
        """
        if self.nix_runtime_libs and "LD_LIBRARY_PATH" not in self.runtime_env:
            libs = ":".join(f"${{pkgs.{p}}}/lib" for p in self.nix_runtime_libs)
            self.runtime_env["LD_LIBRARY_PATH"] = libs

    @property
    def template(self) -> str:
        """The template that renders this spec, named by its payload."""
        return type(self.payload).template_name

    def payload_as(self, kind: type[P]) -> P:
        """
        The payload, checked against the type the calling template expects.

        A template is only ever handed a spec the registry routed to it, so a
        mismatch means the spec was built by hand with the wrong payload — a
        programming error, not a bad recipe, hence TypeError rather than the
        ValueError the adapter raises for malformed config. Fail loudly either
        way: rendering with a foreign payload would silently emit an expression
        built entirely from defaults.
        """
        if not isinstance(self.payload, kind):
            raise TypeError(
                f"{self.pname}: {kind.template_name} template got a "
                f"{type(self.payload).template_name} payload"
            )
        return self.payload
