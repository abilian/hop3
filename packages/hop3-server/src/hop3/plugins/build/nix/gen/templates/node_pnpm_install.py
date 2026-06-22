# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

# ruff: noqa: TRY003, EM101, TC001

"""node-pnpm-install template.

For Node.js applications distributed on the npm registry whose
runtime code assumes pnpm's content-addressed `node_modules/.pnpm/...`
layout. `npm install` produces a flat tree that breaks named ESM
imports of CommonJS modules — symptom:

    SyntaxError: Named export 'Type' not found. The requested module
    '.../.pnpm/@sinclair_typebox@0.34.41/.../index.js' is a CommonJS
    module...

This template seeds a minimal package.json inside the Nix build and
runs `pnpm install --prod --frozen-lockfile` against the npm
registry. The resulting virtual-store layout is preserved verbatim in
the Nix store (never `cp -r`'d — the `.pnpm/` symlinks are
location-independent as long as node_modules/ itself doesn't move).

Requirements for apps using this template:

- `__noChroot = true` is applied automatically (pnpm fetches from the
  npm registry; the Nix sandbox would otherwise block that).
- `--package-import-method=copy` avoids the EPERM-on-chmod issue that
  pnpm's default hardlinks trigger when the source files under
  `~/.local/share/pnpm` have the readonly-bit set.
- Runtime PATH is prepended with `${nodejs}/bin` so the pnpm bin shims
  (which fall back to `node` on PATH) find the correct Node version
  even when the host ships a different one.

Example apps: directus (Node 22, pnpm-layout assumptions), future
Outline / Rocket.Chat releases / Strapi.
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


class NodePnpmInstallTemplate:
    name = "node-pnpm-install"

    def generate(self, spec: AppSpec) -> str:
        if spec.nixpkgs_package is None:
            # We're reusing `nixpkgs_package` to mean "npm package
            # name" since the spec already carries it; semantically
            # distinct but no reason to add yet another field.
            raise ValueError(
                "node-pnpm-install requires nixpkgs_package (interpreted "
                "as npm package name, e.g., 'directus')"
            )
        if spec.exec_target is None:
            raise ValueError(
                "node-pnpm-install requires exec_target (binary name "
                "under node_modules/.bin/, e.g., 'directus')"
            )
        if not spec.version:
            raise ValueError("node-pnpm-install requires version (pinned npm version)")

        npm_pkg = spec.nixpkgs_package  # reinterpreted as npm package name
        runtime_pkg = spec.runtime_package or "nodejs_22"
        pnpm_pkg = "pnpm_9"  # pinned for now; make configurable later if needed

        # Additional npm packages to install alongside the main one
        # (e.g., DB drivers). Passed via `pip_packages` field — the
        # spec's language-agnostic "extras" slot. Semantically
        # "npm install <pkg1> <pkg2>" alongside the primary.
        extras = list(spec.pip_packages)
        all_packages = [f"{npm_pkg}@{spec.version}", *extras]
        deps_json = ",\n          ".join(
            f'"{pkg.split("@")[0]}": "{"@".join(pkg.split("@")[1:]) or "*"}"'
            for pkg in all_packages
        )

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        # Exec line uses the runtime-exported `$APPDIR` (not the `$out` from
        # the Nix build context, which is undefined at wrapper runtime).
        exec_line = f"$APPDIR/node_modules/.bin/{spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        # Splice two bootstrap lines in after the shebang so the wrapper
        # runtime has the correct Node version on PATH and a stable
        # `$APPDIR` handle to the installed tree in the Nix store.
        # APPDIR and NODEBIN are sed-substituted to the real paths at build
        # time (the installPhase below handles both).
        #
        # Note: `${PATH}` must be emitted as the Nix-escape `''${PATH}` so
        # Nix's own ``${...}`` interpolation inside the `'' ... ''` heredoc
        # passes the token through to the generated shell file, where bash
        # resolves it at wrapper runtime.
        shebang, _, rest = wrapper_body.partition("\n")
        bootstrap = (
            # Prepend node first so bin shims that shebang `#!/usr/bin/env node`
            # find the pinned Node version — the canonical failure mode here is
            # directus 11 falling back to the host's Node 18 and hitting an
            # ESM/CJS interop error in @sinclair/typebox.
            "export PATH=\"NODEBIN:''${PATH}\"\n"
            # $APPDIR is the installed app tree under the Nix store. pre-exec
            # commands in hop3.toml should reference `$APPDIR/...`, NOT the
            # Nix build-context `$out/...` (the latter is not set at runtime).
            'APPDIR="APPDIR_PLACEHOLDER"\n'
            "export APPDIR"
        )
        wrapper_body = shebang + "\n\n" + bootstrap + "\n" + rest

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'node-pnpm-install' by hop3-nix-gen.
# Wraps an npm-published package ({npm_pkg}) installed via pnpm
# inside a Nix build with `__noChroot = true` (network access).
# The resulting virtual-store layout is preserved verbatim in the
# Nix store — no `cp -r` (which would break pnpm's relative
# symlinks).
#
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{PINNED_NIXPKGS_HEADER}

let
  nodejs = pkgs.{runtime_pkg};
  pnpm = pkgs.{pnpm_pkg};
  version = "{spec.version}";

  app = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}";
    inherit version;
    __noChroot = true;
    meta.description = "{spec.description}";

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ nodejs pnpm ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3
      cd $out/app

      export HOME=$TMPDIR
      # Both SSL_CERT_FILE and NODE_EXTRA_CA_CERTS are needed: npm
      # reads its own CA bundle via the latter regardless of the
      # former.
      export SSL_CERT_FILE=${{pkgs.cacert}}/etc/ssl/certs/ca-bundle.crt
      export NODE_EXTRA_CA_CERTS=${{pkgs.cacert}}/etc/ssl/certs/ca-bundle.crt

      # Seed a package.json so pnpm has a project to install into.
      cat > package.json << 'JSON'
      {{
        "name": "hop3-{spec.pname}",
        "version": "{spec.version}",
        "private": true,
        "dependencies": {{
          {deps_json}
        }}
      }}
JSON

      # --package-import-method=copy forces copies instead of
      # hardlinks from ~/.local/share/pnpm. Hardlinks inherit
      # pnpm's content-addressed "readonly" mode, which then trips
      # EPERM when pnpm tries to chmod +x the bin shims inside
      # $out/app/node_modules.
      ${{pnpm}}/bin/pnpm install \\
        --config.confirmModulesPurge=false \\
        --config.package-import-method=copy \\
        --prod \\
        --reporter=silent

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      # Runtime must use the Node version we built against — hop3-
      # host's system Node may be older and hit ESM/CJS interop
      # mismatches on the same pnpm tree (directus 11 on Debian's
      # Node 18 is the canonical failure mode).
      #
      # APPDIR_PLACEHOLDER (unique token) gets the nix store path so
      # `$APPDIR` is a stable handle the wrapper exports; NODEBIN is
      # replaced by the pinned Node's bin dir for the PATH prepend.
      sed -i "s|APPDIR_PLACEHOLDER|$out/app|g" $out/bin/{spec.pname}
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
