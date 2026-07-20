# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, TC001

"""node-pnpm-install template.

For Node.js applications distributed on the npm registry whose
runtime code assumes pnpm's content-addressed `node_modules/.pnpm/...`
layout. `npm install` produces a flat tree that breaks named ESM
imports of CommonJS modules — symptom:

    SyntaxError: Named export 'Type' not found. The requested module
    '.../.pnpm/@sinclair_typebox@0.34.41/.../index.js' is a CommonJS
    module...

The app ships a committed `package.json` + `pnpm-lock.yaml`. A
fixed-output derivation runs `pnpm fetch` (which reads only the
lockfile) to populate a store, and the application build then installs
from that store `--offline`, inside the sandbox. The resulting
virtual-store layout is preserved verbatim in the Nix store (never
`cp -r`'d — the `.pnpm/` symlinks are location-independent as long as
node_modules/ itself doesn't move).

Requirements for apps using this template:

- A committed manifest and lockfile: a manifest synthesized during the
  build cannot be locked, so pnpm would re-resolve every semver range
  on each build.
- `--ignore-scripts`: npm postinstall hooks commonly download prebuilt
  binaries, which would reintroduce unpinned content into a sealed build.
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

_NO_LOCKFILE = (
    "{pname}: node-pnpm-install requires a committed manifest and lockfile — "
    'set `node-manifest` and `node-lockfile` in [nix] (e.g. "package.json" '
    'and "pnpm-lock.yaml"). A manifest synthesized at build time cannot be '
    "locked, so pnpm re-resolves every range on each build and the dependency "
    "tree is not reproducible. Generate the pair once with `pnpm install` and "
    "commit both."
)

_NO_DEPS_HASH = (
    "{pname}: node-pnpm-install requires `node-deps-hash` in [nix] — the "
    "sha256 of the fetched pnpm store. Build once with a placeholder "
    '(`node-deps-hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="`) '
    "and read the `got:` hash Nix reports."
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
        if not (spec.node_manifest and spec.node_lockfile):
            raise ValueError(_NO_LOCKFILE.format(pname=spec.pname))
        if not spec.node_deps_hash:
            raise ValueError(_NO_DEPS_HASH.format(pname=spec.pname))

        npm_pkg = spec.nixpkgs_package  # reinterpreted as npm package name
        runtime_pkg = spec.runtime_package or "nodejs_22"
        pnpm_pkg = "pnpm_9"  # pinned for now; make configurable later if needed

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
# Wraps an npm-published package ({npm_pkg}) installed via pnpm from a
# committed lockfile: deps are fetched by a fixed-output derivation and
# the app build itself runs offline inside the sandbox.
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

  manifest = ./{spec.node_manifest};
  lockfile = ./{spec.node_lockfile};

  # Phase 1: fetch the dependency set into a pnpm store. `pnpm fetch` reads
  # only the lockfile, so exactly the recorded versions are downloaded; the
  # derivation's hash then pins that store. This is the only step with
  # network access.
  pnpmStore = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}-pnpm-store";
    inherit version;

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ nodejs pnpm ];

    installPhase = ''
      export HOME=$TMPDIR
      export SSL_CERT_FILE=${{pkgs.cacert}}/etc/ssl/certs/ca-bundle.crt
      export NODE_EXTRA_CA_CERTS=${{pkgs.cacert}}/etc/ssl/certs/ca-bundle.crt
      mkdir -p $TMPDIR/proj && cd $TMPDIR/proj
      cp ${{manifest}} package.json
      cp ${{lockfile}} pnpm-lock.yaml
      mkdir -p $out
      ${{pnpm}}/bin/pnpm fetch --store-dir $out
    '';

    outputHashMode = "recursive";
    outputHashAlgo = "sha256";
    outputHash = "{spec.node_deps_hash}";
  }};

  app = pkgs.stdenv.mkDerivation {{
    # No __noChroot: dependencies come from pnpmStore, so this build is offline.
    pname = "{spec.pname}";
    inherit version;
    meta.description = "{spec.description}";

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ nodejs pnpm ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3
      cd $out/app

      export HOME=$TMPDIR

      # The committed manifest/lockfile pair defines the tree; both are
      # required by `--frozen-lockfile`, which fails if they disagree.
      cp ${{manifest}} package.json
      cp ${{lockfile}} pnpm-lock.yaml

      # --offline: every package must come from pnpmStore, so a dependency
      #   missing from the lockfile fails the build instead of being fetched.
      # --ignore-scripts: postinstall hooks routinely download prebuilt
      #   binaries (node-gyp, esbuild, sharp), which would reintroduce
      #   unpinned, unverified content into a build that is otherwise sealed.
      # --package-import-method=copy forces copies instead of hardlinks from
      #   the store: hardlinks inherit pnpm's content-addressed readonly bit,
      #   which trips EPERM when pnpm chmods the bin shims under $out.
      ${{pnpm}}/bin/pnpm install \\
        --offline \\
        --frozen-lockfile \\
        --ignore-scripts \\
        --store-dir ${{pnpmStore}} \\
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
