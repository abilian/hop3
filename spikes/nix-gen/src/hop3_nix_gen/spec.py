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
    """A source archive or binary to fetch via ``pkgs.fetchurl``."""

    url: str
    sha256: str
    executable: bool = False  # True for single-binary downloads
    unpack: bool = False  # True for tar/zip archives
    unpacker: str | None = None  # e.g., "unzip" for zip archives; None for tar

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
    # Additional path entries (beyond $out/bin)
    extra_paths: list[str] = field(default_factory=list)
