# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

# ruff: noqa: TRY003, EM102, TC001

"""Template protocol and shared helpers used by all templates."""

from __future__ import annotations

import os
from typing import Protocol

from hop3.plugins.build.nix.gen.escaping import nix_escape
from hop3.plugins.build.nix.gen.spec import AppSpec, ConfigFile


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
            raise ValueError(f"ConfigFile {cf.path}: raw format requires raw_content")
        body = nix_escape(cf.raw_content.rstrip("\n") + "\n")
    elif cf.format == "ini":
        body = nix_escape(_format_ini(cf.sections or {}))
    else:
        raise NotImplementedError(f"Config format not yet supported: {cf.format}")

    # Ensure parent directory exists if the path has one
    parent = os.path.dirname(cf.path)
    mkdir_prefix = f"mkdir -p {parent}\n" if parent else ""

    heredoc = f"{mkdir_prefix}cat > {cf.path} << EOF\n{body}EOF"

    if cf.create_if_missing:
        # Wrap in an if-guard (only create if file doesn't exist).
        # Do NOT indent the heredoc body — that would add leading whitespace
        # to every line of the generated config file. Shell heredocs with
        # <<EOF (unquoted) don't care about surrounding indentation.
        return f"if [ ! -f {cf.path} ]; then\n{heredoc}\nfi"

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


def format_nix_runtime_libs(paths: list[str]) -> str:
    """Emit an ``LD_LIBRARY_PATH`` export with Nix-interpolated paths.

    Each entry in ``paths`` is a nixpkgs attribute path (e.g.
    ``"postgresql.lib"``, ``"stdenv.cc.cc.lib"``). The emitted string
    contains raw ``${pkgs.<path>}`` references that Nix interpolates to
    real store paths at build time — **bypassing** ``nix_escape``. The
    ``${LD_LIBRARY_PATH:-}`` reference IS escaped so the shell evaluates
    it at runtime (preserves any existing value, tolerates unset).

    This is the fix for the "pip-installed C extensions under a Nix-
    built Python venv can't find transitive shared libs at runtime"
    class — see ``local-notes/stacks-and-apps/DEFERRED-APPS.md``
    blocker #2. Typical inputs::

        ["postgresql.lib", "krb5.lib", "stdenv.cc.cc.lib"]

    produces::

        export LD_LIBRARY_PATH="${pkgs.postgresql.lib}/lib:${pkgs.krb5.lib}/lib:${pkgs.stdenv.cc.cc.lib}/lib:''${LD_LIBRARY_PATH:-}"
    """
    if not paths:
        return ""
    libs = ":".join(f"${{pkgs.{p}}}/lib" for p in paths)
    return (
        f'export LD_LIBRARY_PATH="{libs}:' + "''${LD_LIBRARY_PATH:-}" + '"'
    )


def format_wrapper_body(
    spec: AppSpec,
    exec_line: str,
) -> str:
    """Build the complete wrapper script body from the spec.

    Structure:
        #!/bin/sh
        <local vars>
        <env exports>
        <nix runtime libs — LD_LIBRARY_PATH with store-path interpolation>
        <config files>
        <pre-exec commands>
        exec <exec_line>
    """
    sections: list[str] = ["#!/bin/sh"]

    local = format_local_vars(spec.local_vars)
    if local:
        sections.append(local)

    exports = format_env_exports(spec)
    if exports:
        sections.append(exports)

    # LD_LIBRARY_PATH goes AFTER env-exports and BEFORE config files /
    # pre-exec / the actual exec line, so any subsequent step that
    # invokes the app's pip-installed Python sees the transitive libs.
    nix_libs = format_nix_runtime_libs(spec.nix_runtime_libs)
    if nix_libs:
        sections.append(nix_libs)

    # Config files are generated BEFORE pre-exec commands because
    # pre-exec may depend on config files (e.g., LimeSurvey's install
    # command needs config.php to know the database connection).
    for cf in spec.config_files:
        sections.append(format_config_file(cf))

    if spec.pre_exec_commands:
        sections.append("\n".join(nix_escape(cmd) for cmd in spec.pre_exec_commands))

    # Escape shell var references in the exec line. Templates that need Nix
    # variables in the exec line (e.g., ${php}/bin/php) must use placeholders
    # like PHPBIN and sed-replace them during the install phase.
    sections.append(f"exec {nix_escape(exec_line)}")

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
    attrs = "\n".join(f'    {key} = "{value}";' for key, value in runtime_env.items())
    return "\n" + attrs + "\n  "


def format_paths_json(extra_paths: list[str]) -> str:
    """Emit the ``path`` array for runtime.json."""
    entries = ['"$out/bin"'] + [f'"{p}"' for p in extra_paths]
    return ",\n    ".join(entries)
