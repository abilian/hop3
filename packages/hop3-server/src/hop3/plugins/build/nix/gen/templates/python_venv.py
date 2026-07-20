# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, TC001

"""python-venv template.

For Python applications that are not in nixpkgs. Builds **hermetically**, in
two phases:

1. A *fixed-output derivation* downloads every wheel/sdist named by a
   hash-pinned lockfile. This is the only step allowed to touch the network,
   and its output is content-addressed, so the set of dependencies is fixed by
   a hash exactly as ``buildGoModule``'s ``vendorHash`` fixes a Go module set.
2. The application build then runs **inside the sandbox with no network**,
   installing from the vendored directory (``--no-index``).

This is what makes the result reproducible: an unpinned ``pip install <name>``
resolves differently from one week to the next, so it can be neither verified
nor rebuilt. The lockfile must carry a hash per requirement (generate with
``uv export --format requirements-txt`` or ``pip-compile --generate-hashes``).

Example apps: Isso, Bugsink.
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec
from hop3.plugins.build.nix.gen.templates.base import (
    PINNED_NIXPKGS_HEADER,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
)

_NO_LOCKFILE = (
    "python-venv requires a hash-pinned lockfile: set `pip-requirements` in "
    '[nix] (e.g. "requirements.txt"). Generate it with '
    "`uv export --format requirements-txt` or `pip-compile --generate-hashes`. "
    "Bare `pip-packages` names are unpinned and unhashed, so the build cannot "
    "be reproduced or run offline."
)

_NO_DEPS_HASH = (
    "python-venv requires `pip-deps-hash` in [nix] — the sha256 of the vendored "
    "dependency set. Build once with "
    '`pip-deps-hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="` '
    "and read the `got:` hash Nix reports."
)


class PythonVenvTemplate:
    name = "python-venv"

    def generate(self, spec: AppSpec) -> str:
        if not spec.pip_requirements:
            raise ValueError(_NO_LOCKFILE)
        if not spec.pip_deps_hash:
            raise ValueError(_NO_DEPS_HASH)
        if spec.exec_target is None:
            raise ValueError("python-venv requires exec_target (e.g., 'isso')")
        runtime_package = spec.runtime_package or "python3"

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"VENVBIN/{spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'python-venv' by hop3-nix-gen.
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{PINNED_NIXPKGS_HEADER}

let
  version = "{spec.version}";
  python = pkgs.{runtime_package};
  requirementsFile = ./{spec.pip_requirements};

  # Phase 1: vendor the dependency set. This fixed-output derivation is the
  # ONLY step with network access; its content hash pins exactly which wheels
  # may enter the build.
  pythonDeps = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}-python-deps";
    inherit version;

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ python pkgs.python3Packages.pip ];

    installPhase = ''
      mkdir -p $out
      pip download --require-hashes --dest $out --requirement ${{requirementsFile}}
    '';

    outputHashMode = "recursive";
    outputHashAlgo = "sha256";
    outputHash = "{spec.pip_deps_hash}";
  }};

  app = pkgs.stdenv.mkDerivation {{
    # No __noChroot: dependencies are vendored above, so this build runs
    # sandboxed and offline.
    pname = "{spec.pname}";
    inherit version;
    meta.description = "{spec.description}";

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ python pkgs.python3Packages.pip ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/venv $out/hop3

      # Create the virtualenv and install offline from the vendored wheels.
      ${{python}}/bin/python -m venv $out/venv
      $out/venv/bin/pip install \\
        --no-index --find-links ${{pythonDeps}} \\
        --require-hashes --requirement ${{requirementsFile}}

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|VENVBIN|$out/venv/bin|g" $out/bin/{spec.pname}
      chmod +x $out/bin/{spec.pname}

      cat > $out/hop3/runtime.json << EOF
{{
  "workers": {{
    "web": "$out/bin/{spec.pname}"
  }},
  "env": {{
{runtime_env_json}
  }},
  "path": [
    {paths_json}
  ]
}}
EOF
    '';
  }};

in
{{
  package = app;

  env = {{{nix_env_attrs}}};
}}
"""
