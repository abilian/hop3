# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, raw-string-in-exception]


"""prebuilt-binary template.

For apps distributed as a single pre-compiled binary downloaded from a URL.
The binary is fetched via ``pkgs.fetchurl { executable = true; }``, copied
to ``$out/bin/<name>``, and wrapped by a shell script that handles runtime
configuration.

Example apps: Miniflux, Gitea.
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec, PrebuiltBinaryPayload
from hop3.plugins.build.nix.gen.templates.base import (
    PINNED_NIXPKGS_HEADER,
    ReproTier,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
)


class PrebuiltBinaryTemplate:
    name = "prebuilt-binary"
    tier = ReproTier.PREBUILT

    def generate(self, spec: AppSpec) -> str:
        p = spec.payload_as(PrebuiltBinaryPayload)
        if p.binary_name is None:
            raise ValueError("prebuilt-binary requires binary_name")

        binding = f"{spec.pname}-bin"
        source_nix = spec.source.as_nix(binding)

        exec_target = spec.exec_target or p.binary_name
        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"BINDIR/{exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'prebuilt-binary' by hop3-nix-gen.
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

    dontUnpack = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      # Install the binary
      cp ${{{binding}}} $out/bin/{p.binary_name}
      chmod +x $out/bin/{p.binary_name}

      # Create wrapper script
      cat > $out/bin/{spec.pname}-wrapper << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|BINDIR|$out/bin|g" $out/bin/{spec.pname}-wrapper
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
