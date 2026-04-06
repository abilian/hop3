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
    # Extra nativeBuildInputs (beyond php and composer). Strings are taken
    # as-is and placed into the Nix attrset, so use full attr paths like
    # "pkgs.nodejs" or "pkgs.unzip".
    extra_native_build_inputs: list[str] = field(default_factory=list)

    # --- nixpkgs-wrapper fields ---
    # Name of the nixpkgs attribute to wrap, e.g., "radicale" for pkgs.radicale
    nixpkgs_package: str | None = None

    # --- node-prebuilt / java-war / python-venv fields ---
    # Nix package attribute for the runtime, e.g., "nodejs_22", "jdk17", "python3"
    runtime_package: str | None = None
    # For node-prebuilt: unpack the tarball without a top-level dir?
    unpack_without_top_level: bool = False
    # For java-war: relative path to the WAR file under $out/app
    war_file: str | None = None
    # For java-war: extra JVM args (go in JAVA_OPTS)
    jvm_default_opts: str | None = None
    # For python-venv: packages to pip install
    pip_packages: list[str] = field(default_factory=list)

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
