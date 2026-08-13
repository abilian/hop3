# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, f-string-in-exception, typing-only-first-party-import]

"""Template protocol and shared helpers used by all templates."""

from __future__ import annotations

import os
from enum import IntEnum
from typing import Protocol

from hop3.plugins.build.nix.gen.escaping import nix_escape
from hop3.plugins.build.nix.gen.spec import AppSpec, ConfigFile

# ---------------------------------------------------------------------------
# Reproducibility tiers
# ---------------------------------------------------------------------------


class ReproTier(IntEnum):
    """
    Where an application's artefact comes from, and who vouches for it.

    Every template builds inside the Nix sandbox against hash-pinned inputs, so
    all three tiers rebuild bit-for-bit. What differs is the *provenance* of the
    running bytes — whether they can be traced back to reviewable source, and
    who did the tracing. That is the question an auditor asks, so it is the axis
    the tiers rank. Lower is better.

    The tier is a property of the template, not of the app, which is what keeps
    the label from drifting: see ``hop3-tools nix tiers`` for the per-app view.
    """

    NIXPKGS = 1
    """Wraps a package nixpkgs already builds from source. Auditable, multi-arch
    and maintained by nixpkgs — the least work and the strongest position, when
    the app is packaged there at a usable version."""

    SOURCE = 2
    """Hop3 compiles the app from source against a hash-pinned dependency set
    (``vendorHash``-style: pip lockfile, composer.lock, pnpm-lock, go.sum,
    gemset.nix, Gradle deps.json). Auditable end to end, at the cost of owning
    the packaging and of lockfiles resolved for one architecture."""

    PREBUILT = 3
    """Fetches an upstream release artefact by sha256. Byte-identical on every
    rebuild, but not auditable: the binary is taken on trust."""


# ---------------------------------------------------------------------------
# Pinned nixpkgs
# ---------------------------------------------------------------------------

# A specific nixpkgs commit, so generated expressions are reproducible across
# hosts and dates instead of resolving the moving `<nixpkgs>` channel through
# NIX_PATH. The sha256 pins the exact bytes — a wrong one fails every build.
# To update: pick a commit and recompute the hash, e.g.
#   nix-prefetch-url --unpack https://github.com/NixOS/nixpkgs/archive/<REV>.tar.gz
NIXPKGS_REV = "50ab793786d9de88ee30ec4e4c24fb4236fc2674"  # nixos-24.11
NIXPKGS_SHA256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx"


def pinned_nixpkgs_header(rev: str | None = None, sha256: str | None = None) -> str:
    """
    The ``{ pkgs ? import (fetchTarball …) {} }:`` header every generated
    expression opens with.

    Defaults to the global pin (``NIXPKGS_REV``/``NIXPKGS_SHA256``). Pass a
    per-app ``rev``/``sha256`` (both together) to override it for an app that
    needs a package the global pin predates — e.g. ``etherpad-lite`` exists in
    nixos-25.05 but not the default nixos-24.11. A caller may still override
    ``pkgs`` at eval time.
    """
    rev = rev or NIXPKGS_REV
    sha256 = sha256 or NIXPKGS_SHA256
    return (
        "{ pkgs ? import (fetchTarball {\n"
        f'  url = "https://github.com/NixOS/nixpkgs/archive/{rev}.tar.gz";\n'
        f'  sha256 = "{sha256}";\n'
        "}) {} }:"
    )


# Back-compat: the default (unoverridden) header, used by templates that don't
# support a per-app pin.
PINNED_NIXPKGS_HEADER = pinned_nixpkgs_header()


class Template(Protocol):
    """A template generates a hop3.nix expression from an AppSpec."""

    name: str
    tier: ReproTier

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


def neutralize_backticks(body: str) -> str:
    r"""
    Make backticks literal in a config body written through an unquoted heredoc.

    The heredoc is unquoted on purpose: ``${VAR}`` and ``$(cmd)`` must expand at
    startup, which is how a config file gets the app's port, database URL and
    generated secrets. Backtick command substitution comes along with that, and
    nothing wants it: it is the legacy spelling of ``$(…)``, no recipe uses it
    deliberately, and a backtick is ordinary punctuation in the prose people
    write around a value.

    So a comment quoting a value the Markdown way became a command. Invoice
    Ninja's recipe explains why its ``APP_URL`` may not be pinned::

        # `http://localhost`, `/` bounced between the app's idea of itself…

    which the shell ran as ``http://localhost``, and the app died at startup with
    ``No such file or directory`` — a wrapper failing on a sentence in a comment.
    Two more recipes carry the same shape in their own comments.

    ``\```` inside an unquoted heredoc emits a literal backtick, so escaping here
    keeps the documented expansions and removes only the one nobody asked for.
    """
    return body.replace("`", "\\`")


def format_config_file(cf: ConfigFile) -> str:
    """
    Emit shell code that writes the config file via heredoc.

    Uses an **unquoted** ``EOF`` marker so shell variables and command
    substitutions are expanded at startup. The ``raw`` format takes the
    literal content string (useful for JSON, YAML, or any format we
    don't have a dedicated formatter for).

    Backticks are neutralised first — see :func:`neutralize_backticks`.
    """
    if cf.format == "raw":
        if cf.raw_content is None:
            raise ValueError(f"ConfigFile {cf.path}: raw format requires raw_content")
        body = nix_escape(neutralize_backticks(cf.raw_content.rstrip("\n") + "\n"))
    elif cf.format == "ini":
        body = nix_escape(neutralize_backticks(_format_ini(cf.sections or {})))
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
    """
    Emit an ``LD_LIBRARY_PATH`` export with Nix-interpolated paths.

    Each entry in ``paths`` is a nixpkgs attribute path (e.g.
    ``"postgresql.lib"``, ``"stdenv.cc.cc.lib"``). The emitted string
    contains raw ``${pkgs.<path>}`` references that Nix interpolates to
    real store paths at build time — **bypassing** ``nix_escape``. The
    ``${LD_LIBRARY_PATH:-}`` reference IS escaped so the shell evaluates
    it at runtime (preserves any existing value, tolerates unset).

    This is the fix for the "pip-installed C extensions under a Nix-
    built Python venv can't find transitive shared libs at runtime"
    class. Typical inputs::

        ["postgresql.lib", "krb5.lib", "stdenv.cc.cc.lib"]

    produces::

        export LD_LIBRARY_PATH="${pkgs.postgresql.lib}/lib:${pkgs.krb5.lib}/lib:${pkgs.stdenv.cc.cc.lib}/lib:''${LD_LIBRARY_PATH:-}"
    """
    if not paths:
        return ""
    libs = ":".join(f"${{pkgs.{p}}}/lib" for p in paths)
    return f'export LD_LIBRARY_PATH="{libs}:' + "''${LD_LIBRARY_PATH:-}" + '"'


def format_wrapper_body(
    spec: AppSpec,
    exec_line: str,
) -> str:
    """
    Build the complete wrapper script body from the spec.

    Structure:
        #!/bin/sh
        <runtime prelude — raw, may reference ${binding} via Nix interp>
        <local vars>
        <env exports>
        <nix runtime libs — LD_LIBRARY_PATH with store-path interpolation>
        <config files>
        <pre-exec commands>
        exec <exec_line>
    """
    # `set -e`: a failing prelude/config/pre-exec step aborts the wrapper instead
    # of falling through to `exec` and serving a half-installed app that only the
    # deploy validation would (later) catch. Fail-loud is the platform default;
    # a step that may fail benignly must say so explicitly (`… || true`), which
    # reads as intent rather than an accident. Not `-u`: wrappers legitimately
    # reference optionally-set vars (addon creds, `${PORT:-8080}` defaults).
    sections: list[str] = ["#!/bin/sh", "set -e"]

    # Runtime prelude is emitted raw (no nix_escape), so `${binding}`
    # references Nix-interpolate at build time. Used by
    # writable-home-at-runtime to lazy-cp the package tree into $PWD
    # before anything else in the wrapper touches the environment.
    if spec.runtime_prelude:
        sections.append(spec.runtime_prelude)

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


def build_writable_home_prelude(
    pname: str,
    source: str,
    env_var: str | None = None,
    cd_into: bool = False,
) -> str:
    """
    Emit the lazy-cp prelude for an app that writes inside its own tree.

    The Nix store is read-only, but plenty of applications expect to write into
    their install directory (Keycloak's Quarkus rebuild, Rails' generated
    config and secret token, xwiki's Jetty logs). Copy the tree into
    ``$PWD/.<pname>-home`` once per app instance, widen the mode, and drop a
    marker so restarts skip the copy.

    ``source`` is emitted verbatim, so it may be a Nix interpolation
    (``${pkg}``) or a sed placeholder the template substitutes later
    (``APPDIR``). ``cd_into`` makes the wrapper run from the writable copy,
    which apps that resolve paths relative to the working directory need.
    """
    lines = [
        f'HOME_DIR="$PWD/.{pname}-home"',
        'if [ ! -f "$HOME_DIR/.hop3-ready" ]; then',
        '  rm -rf "$HOME_DIR"',
        # -rL dereferences symlinks (we need real files to chmod).
        # --no-preserve=ownership drops the nixbld owner; mode is then
        # widened by chmod u+w (capital W just in case).
        f'  cp -rL --no-preserve=ownership {source}/. "$HOME_DIR"',
        '  chmod -R u+w "$HOME_DIR"',
        '  touch "$HOME_DIR/.hop3-ready"',
        "fi",
    ]
    if env_var:
        lines.append(f'export {env_var}="$HOME_DIR"')
    if cd_into:
        lines.append('cd "$HOME_DIR"')
    return "\n".join(lines)


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
