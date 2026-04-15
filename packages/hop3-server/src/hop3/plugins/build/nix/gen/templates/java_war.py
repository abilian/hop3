# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

# ruff: noqa: TRY003, EM101, TC001

"""java-war template.

For Java applications distributed as a single WAR file, executed with a
JDK via ``java -jar file.war``. No unpack needed.

Example apps: Jenkins.
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec
from hop3.plugins.build.nix.gen.templates.base import (
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
)


class JavaWarTemplate:
    name = "java-war"

    def generate(self, spec: AppSpec) -> str:
        if spec.war_file is None:
            raise ValueError("java-war requires war_file (e.g., 'jenkins.war')")
        runtime_package = spec.runtime_package or "jdk17"

        binding = f"{spec.pname}-war"
        source_nix = spec.source.as_nix(binding)

        # Exec line uses JAVABIN and WARPATH placeholders
        # Note: spec.exec_args are appended after -jar WARPATH
        exec_args_str = ""
        if spec.exec_args:
            exec_args_str = " \\\n  " + " \\\n  ".join(spec.exec_args)
        exec_line = f"JAVABIN/java $JAVA_OPTS -jar WARPATH{exec_args_str}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'java-war' by hop3-nix-gen.
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{{ pkgs ? import <nixpkgs> {{}} }}:

let
  version = "{spec.version}";
  jdk = pkgs.{runtime_package};

{source_nix}

  app = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}";
    inherit version;
    meta = {{
      description = "{spec.description}";
    }};

    dontUnpack = true;
    dontBuild = true;

    buildInputs = [ jdk ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3

      cp ${{{binding}}} $out/app/{spec.war_file}

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|JAVABIN|${{jdk}}/bin|g" $out/bin/{spec.pname}
      sed -i "s|WARPATH|$out/app/{spec.war_file}|g" $out/bin/{spec.pname}
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
