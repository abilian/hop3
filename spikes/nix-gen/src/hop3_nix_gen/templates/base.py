"""Template protocol and shared helpers used by all templates."""

from __future__ import annotations

from typing import Protocol

from hop3_nix_gen.escaping import nix_escape
from hop3_nix_gen.spec import AppSpec, ConfigFile


class Template(Protocol):
    """A template generates a hop3.nix expression from an AppSpec."""

    name: str

    def generate(self, spec: AppSpec) -> str:
        """Produce a complete hop3.nix expression as a string."""
        ...


# ---------------------------------------------------------------------------
# Shared formatting helpers
# ---------------------------------------------------------------------------


def format_local_vars(local_vars: dict[str, str]) -> str:
    """Emit local shell variable assignments for the wrapper script top."""
    return "\n".join(
        f'{name}="{nix_escape(value)}"' for name, value in local_vars.items()
    )


def format_env_exports(spec: AppSpec) -> str:
    """Emit ``export NAME=VALUE`` lines and conditional export blocks."""
    lines: list[str] = []

    for name, value in spec.env_exports.items():
        lines.append(f'export {name}="{nix_escape(value)}"')

    for cev in spec.conditional_env_exports:
        if lines:
            lines.append("")
        lines.append(f"# Set {cev.name} only if not already set")
        lines.append(f'if [ -z "${cev.condition_var}" ]; then')
        lines.append(f'  export {cev.name}="{nix_escape(cev.value)}"')
        lines.append("fi")

    return "\n".join(lines)


def format_config_file(cf: ConfigFile) -> str:
    """Emit shell code that writes the config file via heredoc.

    Uses an **unquoted** ``EOF`` marker so shell variables and command
    substitutions are expanded at startup. The ``raw`` format takes the
    literal content string (useful for JSON, YAML, or any format we
    don't have a dedicated formatter for).
    """
    if cf.format == "raw":
        if cf.raw_content is None:
            raise ValueError(
                f"ConfigFile {cf.path}: raw format requires raw_content"
            )
        body = nix_escape(cf.raw_content.rstrip("\n") + "\n")
    elif cf.format == "ini":
        body = nix_escape(_format_ini(cf.sections or {}))
    else:
        raise NotImplementedError(f"Config format not yet supported: {cf.format}")

    # Ensure parent directory exists if the path has one
    import os

    parent = os.path.dirname(cf.path)
    mkdir_prefix = f"mkdir -p {parent}\n" if parent else ""

    heredoc = f"{mkdir_prefix}cat > {cf.path} << EOF\n{body}EOF"

    if cf.create_if_missing:
        # Wrap in an if-guard (only create if file doesn't exist)
        indented = "\n".join("  " + line for line in heredoc.split("\n"))
        return f"if [ ! -f {cf.path} ]; then\n{indented}\nfi"

    return heredoc


def _format_ini(sections: dict[str, dict[str, str]]) -> str:
    """Format a dict-of-dicts as an INI file string."""
    out_lines: list[str] = []
    for section, kvs in sections.items():
        out_lines.append(f"[{section}]")
        for key, value in kvs.items():
            out_lines.append(f"{key} = {value}")
        out_lines.append("")
    return "\n".join(out_lines).rstrip() + "\n"


def format_wrapper_body(
    spec: AppSpec,
    exec_line: str,
) -> str:
    """Build the complete wrapper script body from the spec.

    Structure:
        #!/bin/sh
        <local vars>
        <env exports>
        <pre-exec commands>
        <config files>
        exec <exec_line>
    """
    sections: list[str] = ["#!/bin/sh"]

    local = format_local_vars(spec.local_vars)
    if local:
        sections.append(local)

    exports = format_env_exports(spec)
    if exports:
        sections.append(exports)

    if spec.pre_exec_commands:
        sections.append(
            "\n".join(nix_escape(cmd) for cmd in spec.pre_exec_commands)
        )

    for cf in spec.config_files:
        sections.append(format_config_file(cf))

    sections.append(f"exec {exec_line}")

    return "\n\n".join(sections)


def format_runtime_env_json(runtime_env: dict[str, str]) -> str:
    """Emit the ``env`` portion of runtime.json as JSON lines."""
    if not runtime_env:
        return ""
    items = list(runtime_env.items())
    lines = []
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f'    "{key}": "{value}"{comma}')
    return "\n".join(lines)


def format_nix_env_attrs(runtime_env: dict[str, str]) -> str:
    """Emit the top-level ``env = { ... }`` attribute set."""
    if not runtime_env:
        return ""
    attrs = "\n".join(
        f'    {key} = "{value}";' for key, value in runtime_env.items()
    )
    return "\n" + attrs + "\n  "


def format_paths_json(extra_paths: list[str]) -> str:
    """Emit the ``path`` array for runtime.json."""
    entries = ['"$out/bin"'] + [f'"{p}"' for p in extra_paths]
    return ",\n    ".join(entries)
