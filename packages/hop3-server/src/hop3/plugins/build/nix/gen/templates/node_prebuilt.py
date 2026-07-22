# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, raw-string-in-exception]


"""node-prebuilt template.

For Node.js applications distributed as a tarball with pre-built
``node_modules``. The archive is unpacked into ``$out/app`` and wrapped
with a startup script that runs ``${nodejs}/bin/node`` against the
application entrypoint.

Because the Nix store is read-only, the wrapper typically symlinks
individual app directories (server, node_modules, assets) into the
writable cwd before starting the app. The spec provides this via
``pre_exec_commands``.

Example apps: Wiki.js.
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec, NodePrebuiltPayload
from hop3.plugins.build.nix.gen.templates.base import (
    PINNED_NIXPKGS_HEADER,
    ReproTier,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
)


class NodePrebuiltTemplate:
    name = "node-prebuilt"
    tier = ReproTier.PREBUILT

    def generate(self, spec: AppSpec) -> str:
        p = spec.payload_as(NodePrebuiltPayload)
        if spec.exec_target is None:
            raise ValueError(
                "node-prebuilt requires exec_target (e.g., 'server/index.js')"
            )
        if spec.runtime_package is None:
            spec_runtime = "nodejs_22"
        else:
            spec_runtime = spec.runtime_package

        binding = f"{spec.pname}-src"
        source_nix = spec.source.as_nix(binding)

        # Unpack phase: some Node tarballs have no top-level directory
        if p.unpack_without_top_level:
            unpack_phase = """    unpackPhase = ''
      mkdir -p source
      tar xzf $src -C source
      sourceRoot=source
    '';
"""
        else:
            strip = spec.strip_components
            unpack_phase = f"""    unpackPhase = ''
      tar xzf $src --strip-components={strip}
    '';
"""

        # Exec line uses NODEBIN placeholder (sed-replaced to ${nodejs}/bin)
        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"NODEBIN/node {spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'node-prebuilt' by hop3-nix-gen.
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{PINNED_NIXPKGS_HEADER}

let
  version = "{spec.version}";
  nodejs = pkgs.{spec_runtime};

{source_nix}

  app = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}";
    inherit version;
    meta = {{
      description = "{spec.description}";
    }};

    src = {binding};

    dontBuild = true;
    buildInputs = [ nodejs ];

{unpack_phase}
    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3

      cp -r . $out/app/

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/{spec.pname}
      sed -i "s|NODEBIN|${{nodejs}}/bin|g" $out/bin/{spec.pname}
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
