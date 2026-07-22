# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, TC001

"""prebuilt-archive template.

For apps distributed as a tar.gz or zip archive containing one or more
files. The archive is fetched, unpacked, and specific files are copied
from the unpacked tree to ``$out``.

Example apps: Focalboard, Grafana, Mattermost, Vikunja.
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec, FileMapping
from hop3.plugins.build.nix.gen.templates.base import (
    PINNED_NIXPKGS_HEADER,
    ReproTier,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
)


class PrebuiltArchiveTemplate:
    name = "prebuilt-archive"
    tier = ReproTier.PREBUILT

    def generate(self, spec: AppSpec) -> str:
        if spec.exec_target is None:
            raise ValueError("prebuilt-archive requires exec_target")
        if not spec.file_mappings:
            raise ValueError("prebuilt-archive requires file_mappings")

        binding = f"{spec.pname}-release"
        source_nix = spec.source.as_nix(binding)

        native_build_inputs = ""
        if spec.source.needs_unzip:
            native_build_inputs = "    nativeBuildInputs = [ pkgs.unzip ];\n"

        # Unpack phase. For tar archives, stdenv handles extraction
        # automatically when sourceRoot is set. For zip, we need to unzip
        # explicitly.
        if spec.source.needs_unzip:
            unpack_phase = """    unpackPhase = ''
      unzip $src
    '';
"""
        else:
            # stdenv handles tar extraction automatically
            unpack_phase = ""

        source_root_line = ""
        if spec.source_root:
            source_root_line = f'    sourceRoot = "{spec.source_root}";\n'

        # File copy commands
        copy_lines = []
        for fm in spec.file_mappings:
            copy_lines.append(_format_file_mapping(fm))
        copy_block = "\n".join(copy_lines)

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"BINDIR/{spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'prebuilt-archive' by hop3-nix-gen.
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{PINNED_NIXPKGS_HEADER}

let
  version = "{spec.version}";

{source_nix}

  app = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}";
    inherit version;
    meta = {{
      description = "{spec.description}";
    }};

    src = {binding};
{source_root_line}{native_build_inputs}{unpack_phase}
    installPhase = ''
      mkdir -p $out/bin $out/hop3 $out/share/{spec.pname}

      # Copy files from unpacked archive
{copy_block}

      # Create wrapper script
      cat > $out/bin/{spec.pname}-wrapper << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|BINDIR|$out/bin|g" $out/bin/{spec.pname}-wrapper
      sed -i "s|SHAREDIR|$out/share/{spec.pname}|g" $out/bin/{spec.pname}-wrapper
      chmod +x $out/bin/{spec.pname}-wrapper

      # Write runtime metadata for Hop3
      cat > $out/hop3/runtime.json << EOF
{{
  "workers": {{
    "web": "$out/bin/{spec.pname}-wrapper"
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


def _format_file_mapping(fm: FileMapping) -> str:
    """Emit shell code for a single file copy."""
    recursive = "-r " if fm.recursive else ""
    # Handle glob source
    dest = f"$out/{fm.destination}"
    cmd = f"      cp {recursive}{fm.source} {dest}"
    if fm.executable:
        # After copy, chmod +x
        target = dest
        if fm.source.endswith("/*"):
            target = dest  # All files in dest dir
        cmd += f"\n      chmod +x {target}"
    return cmd
