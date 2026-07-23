# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, raw-string-in-exception]


"""
python-venv template.

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

from hop3.plugins.build.nix.gen.spec import AppSpec, PythonVenvPayload
from hop3.plugins.build.nix.gen.templates.base import (
    ReproTier,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
    pinned_nixpkgs_header,
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
    tier = ReproTier.SOURCE

    def generate(self, spec: AppSpec) -> str:
        p = spec.payload_as(PythonVenvPayload)
        if not p.requirements:
            raise ValueError(_NO_LOCKFILE)
        if not p.deps_hash:
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

{pinned_nixpkgs_header(spec.nixpkgs_rev, spec.nixpkgs_sha256)}

let
  version = "{spec.version}";
  python = pkgs.{runtime_package};
  requirementsFile = ./{p.requirements};

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
    outputHash = "{p.deps_hash}";
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

      # Reproducibility: a C extension built from an sdist embeds pip's random
      # build directory (/build/pip-install-XXXX/...) as the DWARF comp_dir in
      # its .debug_* sections, so two builds of the same source differ byte-for-
      # byte. Strip debug info from ONLY those .so — the ones that actually carry
      # the build path — then rewrite the wheel RECORD hashes to match (else
      # RECORD keeps the pre-strip hash and reintroduces the non-determinism).
      # Prebuilt-wheel extensions are already reproducible and must be left
      # byte-for-byte untouched: re-stripping foreign native libs (Rust cdylibs,
      # mypyc modules) is needless risk, so we skip any .so without the marker.
      find $out/venv -name '*.so' -type f | while read -r so; do
        if grep -qa '/build/pip-' "$so"; then
          ${{pkgs.binutils}}/bin/strip --strip-debug "$so"
        fi
      done
      $out/venv/bin/python - "$out/venv" << 'RECORDFIX'
import base64, hashlib, sys
from pathlib import Path
venv = Path(sys.argv[1])
for record in venv.rglob("RECORD"):
    site = record.parent.parent
    out, changed = [], False
    for line in record.read_text().splitlines():
        cols = line.rsplit(",", 2)
        target = site / cols[0] if len(cols) == 3 else None
        if target and target.suffix == ".so" and target.is_file():
            data = target.read_bytes()
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
            new = f"{{cols[0]}},sha256={{digest.rstrip(b'=').decode()}},{{len(data)}}"
            changed = changed or new != line
            line = new
        out.append(line)
    if changed:
        record.write_text("\\n".join(out) + "\\n")
RECORDFIX

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
