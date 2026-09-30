# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, f-string-in-exception, typing-only-first-party-import]

"""Template protocol and shared helpers used by all templates."""

from __future__ import annotations

import json
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
# To update: take the head of a `nixos-YY.MM` branch (Hydra-tested), recompute
# the hash, and re-record every dependency hash in one pass (each is a function
# of the toolchain that produced it):
#   nix-prefetch-url --unpack https://github.com/NixOS/nixpkgs/archive/<REV>.tar.gz
# NIXPKGS_RELEASE names the release, and a test fails once it falls more than
# two releases behind: the last pin expired silently, as unrelated-looking
# failures in whichever app touched the stale part next.
NIXPKGS_RELEASE = "26.05"
NIXPKGS_REV = "c508844df6c28fa6dabc1b6af70f3ccbd65c5201"  # nixos-26.05, 2026-09-24
NIXPKGS_SHA256 = "1qna2ba5v8vg2hbw1kvylgajfwmiv83mx3jwfplwblzlgimhvvp9"


def pinned_nixpkgs_header(rev: str | None = None, sha256: str | None = None) -> str:
    """
    The ``{ pkgs ? import (fetchTarball …) {} }:`` header every generated
    expression opens with.

    Defaults to the global pin (``NIXPKGS_REV``/``NIXPKGS_SHA256``). Pass a
    per-app ``rev``/``sha256`` (both together) to override it for an app that
    needs a package the global pin predates — e.g. ``etherpad-lite`` exists in
    one release but not in the default. A caller may still override
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


def generated_line(template: str) -> str:
    """The header line that marks an expression as generated from ``template``."""
    return f"# GENERATED from template '{template}' by hop3-nix-gen."


def eject_hint(pname: str) -> str:
    """The header line that says how to take the expression over by hand."""
    return f"# Run 'hop3 nix eject --app {pname} > hop3.nix' to edit it by hand."


def ejected(expression: str, template: str, pname: str, date: str) -> str:
    """
    A generated expression, re-headed as a file its owner now edits.

    Rewrites the two header lines every template emits, wherever the template
    puts them: prose between them once left half the templates unchanged.
    """
    return expression.replace(
        generated_line(template), f"# Ejected from template '{template}' on {date}."
    ).replace(
        eject_hint(pname),
        "# Yours to edit. Remove the [nix] section from hop3.toml: a build\n"
        "# refuses an app that has both.",
    )


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


#: The generated expression's own filename. The builder writes it into the
#: app's source directory before building, so an unfiltered `./.` makes every
#: expression part of its own input.
_GENERATED_EXPR_NAME = "hop3.nix"


def local_source_expr() -> str:
    """
    The ``src`` for an app built from its own recipe directory.

    A bare ``./.`` copies the whole working directory into the store, and two
    things in there do not belong:

    - **`.git`**. ``hop3 launch <repo-url>`` clones into the app's source
      directory and nothing strips it afterwards (`core.git.clone_repository`).
      Packfiles are not byte-stable across clones, so identical code yields a
      different derivation; and `.git/config` holds the remote URL, token
      included if the URL carried one, in a world-readable store.
      ``lib.cleanSource`` drops it, with editor backups and `result` symlinks.
    - **the generated expression itself**, which `nix.builder` writes into the
      source directory before building. Without this a change to the generator
      alters the `src` hash of every app it emits, so `nix build --rebuild`
      compares two different derivations.

    What is *not* in here, though it looks as if it should be: the app's
    runtime droppings. A worker's working directory is this same source
    directory, so a deployed app writes its generated config, its SQLite file
    and its `data/` inside a future `src` — but every deploy clears and
    re-extracts `src/` before building
    (:func:`hop3.lib.archives.extract_archive_to_dir`), so none of it survives
    to the build. That makes this list closed rather than best-effort.
    """
    return (
        "pkgs.lib.cleanSourceWith {\n"
        "      src = pkgs.lib.cleanSource ./.;\n"
        "      filter = path: _type:\n"
        f'        baseNameOf (toString path) != "{_GENERATED_EXPR_NAME}";\n'
        "    }"
    )


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


BEFORE_RUN_FLAG = "--hop3-before-run"


def has_before_run(spec: AppSpec) -> bool:
    """Whether the wrapper has a before-run phase: files to write, steps to run."""
    return bool(spec.config_files or spec.pre_exec_commands)


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
        if [ "$1" = "--hop3-before-run" ]; then
        <config files>
        <pre-exec commands>
        exit 0
        fi
        exec <exec_line>

    The config files and pre-exec commands are the deploy's business, not the
    process's: runtime.json names ``<wrapper> --hop3-before-run`` as a
    before-run step, so Hop3 runs them once per deploy, with the app's full
    environment and before the workers start. They used to run on every start,
    which put them inside the health-check window (BookStack's migrations
    outlasted it) and made the running app the author of files the next deploy
    replaces.
    """
    # `set -e`: a failing prelude/config/pre-exec step aborts the wrapper instead
    # of falling through to `exec` and serving a half-installed app that only the
    # deploy validation would (later) catch. Fail-loud is the platform default;
    # a step that may fail benignly must say so explicitly (`… || true`), which
    # reads as intent rather than an accident. Not `-u`: wrappers legitimately
    # reference optionally-set vars (addon creds, `${PORT:-8080}` defaults).
    sections: list[str] = ["#!/bin/sh", "set -e"]

    # Runtime prelude is emitted raw (no nix_escape), so `${binding}`
    # references Nix-interpolate at build time: JAVA_HOME="${jdk}", say.
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

    if has_before_run(spec):
        sections.append(f'if [ "$1" = "{BEFORE_RUN_FLAG}" ]; then')
        # Config files are generated BEFORE pre-exec commands because
        # pre-exec may depend on config files (e.g., LimeSurvey's install
        # command needs config.php to know the database connection).
        sections.extend(format_config_file(cf) for cf in spec.config_files)
        sections.extend(nix_escape(cmd) for cmd in spec.pre_exec_commands)
        sections.append("exit 0\nfi")

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


def format_runtime_json(
    spec: AppSpec,
    wrapper: str,
    *,
    runtime_env: dict[str, str] | None = None,
    writable_tree: str = "",
    php_fpm: dict[str, str] | None = None,
) -> str:
    """
    The heredoc that writes ``$out/hop3/runtime.json``, the build's contract.

    ``wrapper`` is the web worker's path under ``$out``. When the wrapper has a
    before-run phase, the same path with ``--hop3-before-run`` is the artifact's
    before-run step. ``runtime_env`` defaults to the spec's; ``writable_tree``
    names the store tree Hop3 copies into the app's directory at deploy time.
    ``php_fpm`` asks Hop3 for a php-fpm pool as the web worker in place of the
    wrapper; the Nix builder documents its keys.
    """
    env_json = format_runtime_env_json(
        spec.runtime_env if runtime_env is None else runtime_env
    )
    tree = f'\n  "writable_tree": "{writable_tree}",' if writable_tree else ""
    before_run = (
        f'\n  "before_run": ["{wrapper} {BEFORE_RUN_FLAG}"],'
        if has_before_run(spec)
        else ""
    )
    if php_fpm:
        web = f'\n  "php_fpm": {json.dumps(php_fpm)},\n  "workers": {{}},'
    else:
        web = f'\n  "workers": {{\n    "web": "{wrapper}"\n  }},'
    return f"""      cat > $out/hop3/runtime.json << EOF
{{{tree}{before_run}{web}
  "env": {{
{env_json}
  }},
  "path": [
    {format_paths_json(spec.extra_paths)}
  ]
}}
EOF"""
