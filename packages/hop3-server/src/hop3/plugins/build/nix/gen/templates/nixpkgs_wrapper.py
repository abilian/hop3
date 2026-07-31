# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, raw-string-in-exception]


"""
nixpkgs-wrapper template.

For applications already available as nixpkgs packages (e.g., Radicale).
No source fetching or building is needed — we just wrap the existing
package with Hop3's runtime.json metadata and a thin startup wrapper.

This pattern is fundamentally different from the build-from-source
templates: the nixpkgs ecosystem has already done the packaging work,
and we just need to provide the hop3-specific runtime plumbing.

Example apps: Radicale (pkgs.radicale).
"""

from __future__ import annotations

import dataclasses

from hop3.plugins.build.nix.gen.spec import AppSpec, NixpkgsWrapperPayload
from hop3.plugins.build.nix.gen.templates.base import (
    ReproTier,
    build_writable_home_prelude,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
    pinned_nixpkgs_header,
)


class NixpkgsWrapperTemplate:
    name = "nixpkgs-wrapper"
    tier = ReproTier.NIXPKGS

    def generate(self, spec: AppSpec) -> str:
        p = spec.payload_as(NixpkgsWrapperPayload)
        if p.package is None:
            raise ValueError("nixpkgs-wrapper requires nixpkgs_package")
        if spec.exec_target is None:
            raise ValueError("nixpkgs-wrapper requires exec_target (binary name)")

        pkg_attr = p.package
        binding = spec.pname.replace("-", "_")

        # `pkgs.<pkg>` or `pkgs.<pkg>.override { ... }` depending on
        # whether the app needs to pass build-time config down to the
        # nixpkgs derivation (Keycloak's confFile, Jenkins's extraPlugins,
        # etc.). Override values are emitted raw so they can reference
        # `pkgs`, `writeText`, etc. at Nix evaluation time.
        if p.overrides:
            override_attrs = "\n".join(
                f"    {key} = {value};" for key, value in p.overrides.items()
            )
            package_expr = f"pkgs.{pkg_attr}.override {{\n{override_attrs}\n  }}"
        else:
            package_expr = f"pkgs.{pkg_attr}"

        # writable-home-at-runtime synthesizes a runtime prelude and
        # flips PKGBIN to a runtime-resolved path. The prelude uses
        # `${binding}` (Nix-interpolated to the store source path) and
        # `$HOME_DIR` (expanded at wrapper runtime, not Nix build time).
        # `exec-prefix` is still respected if the user set it — it
        # overrides even the writable-home path, for apps that want a
        # custom layout under the writable home.
        prelude_parts: list[str] = []
        if spec.writable_home_at_runtime:
            prelude_parts.append(
                build_writable_home_prelude(
                    spec.pname, f"${{{binding}}}", spec.writable_home_env_var
                )
            )
            # The `\\$` produces a literal `\$` in the Nix `''` string,
            # which the shell running sed sees as `\$` inside `"…"` →
            # `$` literal. sed then writes `$HOME_DIR/bin` unexpanded
            # into the wrapper, where bash expands it at exec time.
            default_pkgbin = "\\$HOME_DIR/bin"
        else:
            default_pkgbin = f"${{{binding}}}/bin"

        # env-exports-raw: values are Nix-interpolated at build time
        # (unlike env-exports which are nix_escape'd). Useful for
        # referencing extra let-bindings — e.g., JAVA_HOME="${jdk}".
        if p.env_exports_raw:
            prelude_parts.append(
                "\n".join(f'export {k}="{v}"' for k, v in p.env_exports_raw.items())
            )

        if prelude_parts:
            spec = dataclasses.replace(spec, runtime_prelude="\n\n".join(prelude_parts))

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"PKGBIN/{spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)
        # PKGBIN defaults to the upstream package's bin dir. install-extra
        # callers that bake artefacts under $out (e.g., Keycloak's
        # $out/keycloak-home) override this with exec-prefix so the
        # wrapper execs the baked tree instead.
        pkgbin_replacement = p.exec_prefix or default_pkgbin
        install_extra_block = (
            f"\n      # --- install-extra (hop3.toml [nix].install-extra) ---\n"
            f"{p.install_extra}\n"
            if p.install_extra
            else ""
        )

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        # Extra let-bindings (e.g., `jdk = pkgs.zulu21;`). Emitted raw
        # so Nix evaluates the RHS at build time. Indented to match
        # the existing `{binding} = {package_expr};` line below.
        let_extra_lines = "\n".join(
            f"  {key} = {value};" for key, value in p.let_extra.items()
        )
        let_extra_block = f"\n{let_extra_lines}" if let_extra_lines else ""

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

{pinned_nixpkgs_header(spec.nixpkgs_rev, spec.nixpkgs_sha256)}

let
  {binding} = {package_expr};
  # A STABLE name for the wrapped package, for recipes to reference.
  #
  # `{binding}` above is derived from the app id (dashes to underscores), so it
  # renames whenever the app does — and a recipe that spelled the old name out
  # in `extra-paths` or `env-exports-raw` then fails at BUILD time with a bare
  # Nix `undefined variable`, naming a line the recipe author never wrote.
  # keycloak-nixgen and mattermost-nixgen were both created by copying a recipe
  # and renaming the app; both carried `${{keycloak}}`/`${{mattermost}}` into a
  # tree whose binding had become `keycloak_nixgen`/`mattermost_nixgen`.
  # Reference `${{pkg}}` and the app id stops being part of the contract.
  pkg = {binding};{let_extra_block}

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
