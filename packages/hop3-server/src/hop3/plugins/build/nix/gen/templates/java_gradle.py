# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0


"""
java-gradle template.

Builds a Java application **from source** with Gradle, then runs the produced
jar with ``java -jar``. This is the JVM counterpart to ``go-source`` /
``php-app`` — the app is compiled by Hop3, not downloaded as a prebuilt dist
(the ``java-war`` template) nor wrapped from nixpkgs.

Gradle's dependency downloads are pinned by a committed ``deps.json`` lockfile
(nixpkgs' ``gradle.fetchDeps`` / ``mitmCache`` format — the analogue of
``buildGoModule``'s ``vendorHash``), so the build is hermetic and offline. A
``deps.json`` for a pinned version can be reused verbatim from nixpkgs.

Example apps: Stirling-PDF.
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec, JavaGradlePayload
from hop3.plugins.build.nix.gen.templates.base import (
    ReproTier,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
    pinned_nixpkgs_header,
)

_NO_JAR = (
    "{pname}: java-gradle requires `gradle-jar-glob` (the built jar to install, "
    "e.g. 'build/libs/App-*.jar') and `gradle-jar-name` (its installed name) "
    "in [nix]."
)


def _nix_list(values: list[str]) -> str:
    return " ".join(f'"{v}"' for v in values)


class JavaGradleTemplate:
    name = "java-gradle"
    tier = ReproTier.SOURCE

    def generate(self, spec: AppSpec) -> str:
        p = spec.payload_as(JavaGradlePayload)
        if not (p.jar_glob and p.jar_name):
            raise ValueError(_NO_JAR.format(pname=spec.pname))
        runtime_package = spec.runtime_package or "jre"

        binding = f"{spec.pname.replace('-', '_')}_src"
        source_nix = spec.source.as_nix(binding)

        patches = " ".join(f"./{patch}" for patch in p.patches)
        patches_attr = f"\n    patches = [ {patches} ];" if patches else ""
        flags_attr = f"\n    gradleFlags = [ {_nix_list(p.flags)} ];" if p.flags else ""

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"JAVABIN/java $JAVA_OPTS -jar JARPATH{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'java-gradle' by hop3-nix-gen.
# Compiled from source with Gradle: the dependency set is pinned by a committed
# deps.json lockfile, so the build is hermetic and offline.
#
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{pinned_nixpkgs_header(spec.nixpkgs_rev, spec.nixpkgs_sha256)}

let
  version = "{spec.version}";
  jre = pkgs.{runtime_package};

{source_nix}

  # Compiled here, not downloaded: a prebuilt jar/dist cannot be audited. The
  # Gradle dependency set is pinned by ./{p.deps_json} (fetched once
  # into the mitm cache), so the compile runs offline in the sandbox.
  jar = pkgs.stdenv.mkDerivation (finalAttrs: {{
    pname = "{spec.pname}";
    inherit version;
    src = {binding};{patches_attr}

    mitmCache = pkgs.gradle.fetchDeps {{
      inherit (finalAttrs) pname;
      data = ./{p.deps_json};
    }};
    __darwinAllowLocalNetworking = true;{flags_attr}
    # Upstream test suites often need network or extra services; skip them here
    # so the build stays hermetic.
    doCheck = false;

    nativeBuildInputs = [ pkgs.gradle pkgs.gradle.jdk ];

    installPhase = ''
      install -Dm644 {p.jar_glob} $out/{p.jar_name}
    '';
  }});

  app = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}";
    inherit version;
    meta.description = "{spec.description}";

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|JAVABIN|${{jre}}/bin|g" $out/bin/{spec.pname}
      sed -i "s|JARPATH|${{jar}}/{p.jar_name}|g" $out/bin/{spec.pname}
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
