# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

# ruff: noqa: TRY003, EM101, TC001

"""nixpkgs-wrapper template.

For applications already available as nixpkgs packages (e.g., Radicale).
No source fetching or building is needed — we just wrap the existing
package with Hop3's runtime.json metadata and a thin startup wrapper.

This pattern is fundamentally different from the build-from-source
templates: the nixpkgs ecosystem has already done the packaging work,
and we just need to provide the hop3-specific runtime plumbing.

Example apps: Radicale (pkgs.radicale).
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec
from hop3.plugins.build.nix.gen.templates.base import (
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
)


class NixpkgsWrapperTemplate:
    name = "nixpkgs-wrapper"

    def generate(self, spec: AppSpec) -> str:
        if spec.nixpkgs_package is None:
            raise ValueError("nixpkgs-wrapper requires nixpkgs_package")
        if spec.exec_target is None:
            raise ValueError("nixpkgs-wrapper requires exec_target (binary name)")

        pkg_attr = spec.nixpkgs_package
        binding = spec.pname.replace("-", "_")

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"PKGBIN/{spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)
        # PKGBIN defaults to the upstream package's bin dir. install-extra
        # callers that bake artefacts under $out (e.g., Keycloak's
        # $out/keycloak-home) override this with exec-prefix so the
        # wrapper execs the baked tree instead.
        pkgbin_replacement = (
            spec.exec_prefix or f"${{{binding}}}/bin"
        )
        install_extra_block = (
            f"\n      # --- install-extra (hop3.toml [nix].install-extra) ---\n"
            f"{spec.install_extra}\n"
            if spec.install_extra
            else ""
        )

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        # Use the upstream package's version if no version is declared.
        version_line = (
            f'version = "{spec.version}"'
            if spec.version
            else f"version = {binding}.version"
        )

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'nixpkgs-wrapper' by hop3-nix-gen.
# Wraps the existing nixpkgs package (pkgs.{pkg_attr}) with Hop3 runtime
# metadata. No source fetching or building needed — the package is
# already available in nixpkgs.
#
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{{ pkgs ? import <nixpkgs> {{}} }}:

let
  {binding} = pkgs.{pkg_attr};

  app = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}";
    {version_line};
    meta.description = "{spec.description}";

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      # Replace placeholders PKGBIN and PKGOUT with the upstream
      # nixpkgs package paths (binary directory and root directory).
      # PKGBIN is overridable via [nix].exec-prefix for install-extra
      # recipes that bake the runnable into $out at package time.
      sed -i "s|PKGBIN|{pkgbin_replacement}|g" $out/bin/{spec.pname}
      sed -i "s|PKGOUT|${{{binding}}}|g" $out/bin/{spec.pname}
      chmod +x $out/bin/{spec.pname}
{install_extra_block}
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
