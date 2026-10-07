# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, raw-string-in-exception]


"""
node-pnpm-install template.

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
  A source-only node-gyp addon (e.g. isolated-vm) is therefore left
  uncompiled; declare it in `node-native-packages` to have it built from
  source, offline, with the C/C++ toolchain (see `_native_addon_build`).
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

from hop3.plugins.build.nix.gen.spec import AppSpec, NodePnpmInstallPayload
from hop3.plugins.build.nix.gen.templates.base import (
    ReproTier,
    eject_hint,
    format_nix_env_attrs,
    format_runtime_json,
    format_wrapper_body,
    generated_line,
    local_source_expr,
    pinned_nixpkgs_header,
)

# lockfileVersion each pnpm major reads and writes. Measured, not assumed:
# pnpm 8 emits 6.0; pnpm 9, 10 and 11 all emit 9.0, so a lockfile is portable
# across those three. A recipe pinning pnpm_8 with a 9.0 lockfile (or the
# reverse) fails inside the build with a parse error that names neither cause.
PNPM_LOCKFILE_VERSIONS = {
    "pnpm_8": "6.0",
    "pnpm_9": "9.0",
    "pnpm_10": "9.0",
    "pnpm_11": "9.0",
}


def lockfile_version_for(pnpm_package: str) -> str | None:
    """The lockfileVersion the given nixpkgs pnpm attribute expects."""
    return PNPM_LOCKFILE_VERSIONS.get(pnpm_package)


def parse_lockfile_version(lockfile_text: str) -> str | None:
    """Read `lockfileVersion:` from a pnpm-lock.yaml."""
    for line in lockfile_text.splitlines():
        if line.startswith("lockfileVersion:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return None


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


def _native_addon_build(payload: NodePnpmInstallPayload) -> tuple[str, str]:
    """
    Toolchain inputs + rebuild step for node-gyp native addons.

    Returns ``("", "")`` when the recipe declares none. Otherwise returns the
    extra ``nativeBuildInputs`` fragment (C/C++ toolchain) and the shell block
    that compiles exactly the declared packages from source, offline, against
    the pinned Node headers. The compiled ``.node`` lands at a deterministic
    sandbox path, so it is bit-for-bit reproducible with no post-processing.
    """
    packages = payload.native_packages
    if not packages:
        return "", ""

    # node-gyp needs python + make + a C/C++ compiler; the gcc wrapper supplies
    # both `cc` and `g++`. The pinned Node's headers reach node-gyp via
    # `npm_config_nodedir`.
    build_inputs = " pkgs.python3 pkgs.gnumake pkgs.gcc"
    targets = " ".join(packages)
    rebuild = f"""
      # Native addons: the sealed install above ran with --ignore-scripts, so a
      # source-only node-gyp package (e.g. isolated-vm) was left uncompiled.
      # Build exactly the declared ones here — offline, from source, against the
      # pinned Node's headers. Packages that ship a prebuilt `.node` need no
      # entry; only those that must be compiled do.
      #
      # pnpm 10 runs no dependency's build script it has not been told to
      # approve, and `rebuild` then skips the package without a word: the build
      # succeeded and the app died at start on `Cannot find module
      # './out/isolated_vm'`. The approval that would live in the lockfile
      # cannot be written under a frozen install, so this one command allows
      # builds; it rebuilds only the packages named here. pnpm 9 ignores the key.
      export npm_config_nodedir=${{nodejs}}
      export CI=true
      ${{pnpm}}/bin/pnpm rebuild --config.dangerouslyAllowAllBuilds=true \\
        --store-dir $PNPM_STORE {targets}
"""
    return build_inputs, rebuild


class NodePnpmInstallTemplate:
    name = "node-pnpm-install"
    tier = ReproTier.SOURCE

    def generate(self, spec: AppSpec) -> str:
        p = spec.payload_as(NodePnpmInstallPayload)
        if p.npm_package is None and not p.local_source:
            raise ValueError(
                "node-pnpm-install requires npm-package (the package to "
                "install from the registry, e.g. 'directus'), or "
                "`node-local-source = true` for an app that IS this directory"
            )
        if spec.exec_target is None:
            raise ValueError(
                "node-pnpm-install requires exec_target: the binary name under "
                "node_modules/.bin/ (e.g. 'directus'), or — with "
                "`node-local-source` — the app's own entry script "
                "(e.g. 'server.js')"
            )
        if not spec.version:
            raise ValueError("node-pnpm-install requires version (pinned npm version)")
        if not (p.manifest and p.lockfile):
            raise ValueError(_NO_LOCKFILE.format(pname=spec.pname))
        if not p.deps_hash:
            raise ValueError(_NO_DEPS_HASH.format(pname=spec.pname))

        # The app's own directory becomes the build input. Copied in BEFORE
        # `pnpm install`, which populates `node_modules` in this same tree —
        # copying afterwards would overwrite it.
        src_attr = f"\n    src = {local_source_expr()};" if p.local_source else ""
        app_install = (
            "\n      # The application's own code, from the recipe directory."
            "\n      cp -r $src/. $out/app/"
            # Store files are read-only, and the install below writes into
            # this tree (the manifest, the lockfile, node_modules).
            "\n      chmod -R u+w $out/app"
            if p.local_source
            else ""
        )

        what = (
            "The application in this directory, with its dependencies"
            if p.local_source
            else f"Wraps an npm-published package ({p.npm_package})"
        )
        runtime_pkg = spec.runtime_package or "nodejs_22"
        pnpm_pkg = p.pnpm_package

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        # Exec line uses the runtime-exported `$APPDIR` (not the `$out` from
        # the Nix build context, which is undefined at wrapper runtime).
        #
        # A registry app's entry point is a bin shim its package installed; a
        # local app's is a file it wrote, so `exec-target` names that file and
        # node runs it. Hardcoding the `node_modules/.bin/` prefix would make
        # the local case unexpressible — there is no shim for `server.js`.
        exec_line = (
            f"node $APPDIR/{spec.exec_target}{exec_args}"
            if p.local_source
            else f"$APPDIR/node_modules/.bin/{spec.exec_target}{exec_args}"
        )
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

        runtime_json = format_runtime_json(spec, f"$out/bin/{spec.pname}")
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)

        native_build_inputs, native_rebuild = _native_addon_build(p)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
{generated_line("node-pnpm-install")}
# {what} installed via pnpm from a
# committed lockfile: deps are fetched by a fixed-output derivation and
# the app build itself runs offline inside the sandbox.
# The resulting virtual-store layout is preserved verbatim in the
# Nix store — no `cp -r` (which would break pnpm's relative
# symlinks).
#
{eject_hint()}

{pinned_nixpkgs_header(spec.nixpkgs_rev, spec.nixpkgs_sha256)}

let
  nodejs = pkgs.{runtime_pkg};
  pnpm = pkgs.{pnpm_pkg};
  version = "{spec.version}";

  manifest = ./{p.manifest};
  lockfile = ./{p.lockfile};

  # Phase 1: fetch the dependency set into a pnpm store. `pnpm fetch` reads
  # only the lockfile, so exactly the recorded versions are downloaded; the
  # derivation's hash then pins that store. This is the only step with
  # network access.
  pnpmStore = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}-pnpm-store";
    inherit version;

    dontUnpack = true;
    dontBuild = true;
    # Vendored content must be byte-preserved: stdenv's default fixupPhase runs
    # patchShebangs over $out, which rewrites the `#!/usr/bin/env bash` shebang
    # of npm packages' shipped scripts (stored in pnpm's CAFS as `*-exec` files)
    # to an absolute `/nix/store/…-bash` path — a store reference a fixed-output
    # derivation may not contain (and a source of hash drift). Skip fixup, as
    # nixpkgs' own pnpm.fetchDeps does.
    dontFixup = true;

    nativeBuildInputs = [ nodejs pnpm ];

    installPhase = ''
      export HOME=$TMPDIR
      export SSL_CERT_FILE=${{pkgs.cacert}}/etc/ssl/certs/ca-bundle.crt
      export NODE_EXTRA_CA_CERTS=${{pkgs.cacert}}/etc/ssl/certs/ca-bundle.crt
      mkdir -p $TMPDIR/proj && cd $TMPDIR/proj
      cp ${{manifest}} package.json
      cp ${{lockfile}} pnpm-lock.yaml

      # pnpm 9's `fetch` compiles native addons while populating the store,
      # which puts a C++ toolchain, kernel headers and a compiler's idea of
      # file permissions inside a *fixed-output* derivation. An FOD is the
      # sanctioned escape from purity: it gets network access, and in exchange
      # Nix verifies only its output hash, so its content must be a download
      # and nothing else. directus-nixgen's store built once in August and was
      # never re-entered — nine green runs off one store path — until a rebuild
      # emptied the store and `isolated-vm@5.0.3` failed to compile here.
      #
      # The config file rather than a CLI flag: `pnpm fetch --help` documents
      # no scripts option and the command is marked experimental, so the knob
      # that survives a pnpm upgrade is the one pnpm reads from disk. Native
      # addons are built where they belong, in the pure derivation below, from
      # `node-native-packages`.
      printf 'ignore-scripts=true\\n' > .npmrc

      mkdir -p $out
      ${{pnpm}}/bin/pnpm fetch --store-dir $out

      # Reproducibility: `pnpm fetch` stamps a `checkedAt` verification
      # timestamp into every store index file and leaves their key order
      # unstable, so the fixed-output hash drifts run-to-run (and the app build
      # then fails its own vendorHash check on a rebuild). Normalize exactly as
      # nixpkgs' own pnpm.fetchDeps does — drop the temp dirs, strip `checkedAt`
      # at any depth, sort keys — so the vendored store is byte-stable.
      #
      # pnpm 10 also registers the project it fetched for under
      # `v10/projects/<hash of its path>`. The path is the build directory,
      # which differs per build wherever the sandbox does not pin it to /build
      # (the Docker target, macOS), so the hash changed on every fetch of an
      # unchanged lockfile. It points at a directory gone after the build and
      # carries no package content.
      rm -rf $out/v3/tmp $out/v10/tmp $out/v10/projects
      find $out -name '*.json' -type f | while read -r f; do
        ${{pkgs.jq}}/bin/jq --sort-keys 'del(.. | .checkedAt?)' "$f" > "$f.norm"
        mv "$f.norm" "$f"
      done
    '';

    outputHashMode = "recursive";
    outputHashAlgo = "sha256";
    outputHash = "{p.deps_hash}";
  }};

  app = pkgs.stdenv.mkDerivation {{
    # No __noChroot: dependencies come from pnpmStore, so this build is offline.
    pname = "{spec.pname}";
    inherit version;
    meta.description = "{spec.description}";

    dontUnpack = true;
    dontBuild = true;{src_attr}

    nativeBuildInputs = [ nodejs pnpm{native_build_inputs} ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3
      cd $out/app
{app_install}
      export HOME=$TMPDIR

      # The committed manifest/lockfile pair defines the tree; both are
      # required by `--frozen-lockfile`, which fails if they disagree.
      cp ${{manifest}} package.json
      cp ${{lockfile}} pnpm-lock.yaml

      # pnpm 10 writes into its store even when installing offline, and the
      # fetched store is a read-only store path: installing from it directly
      # fails with EACCES (exit code 243). Install from a writable copy, as
      # nixpkgs' own pnpmConfigHook does.
      export PNPM_STORE=$TMPDIR/pnpm-store
      cp -Tr ${{pnpmStore}} $PNPM_STORE
      chmod -R +w $PNPM_STORE

      # --offline: every package must come from pnpmStore, so a dependency
      #   missing from the lockfile fails the build instead of being fetched.
      # --ignore-scripts: postinstall hooks routinely download prebuilt
      #   binaries (node-gyp, esbuild, sharp), which would reintroduce
      #   unpinned, unverified content into a build that is otherwise sealed.
      # --package-import-method=copy forces copies instead of hardlinks from
      #   the store: hardlinks inherit pnpm's content-addressed readonly bit,
      #   which trips EPERM when pnpm chmods the bin shims under $out.
      # --reporter=append-only: no progress bars in a build log, and unlike
      #   `silent` it keeps the errors. `silent` turned a failed install into
      #   "builder failed with exit code 243" and nothing else.
      ${{pnpm}}/bin/pnpm install \\
        --offline \\
        --frozen-lockfile \\
        --ignore-scripts \\
        --store-dir $PNPM_STORE \\
        --config.confirmModulesPurge=false \\
        --config.package-import-method=copy \\
        --prod \\
        --reporter=append-only
{native_rebuild}
      # Reproducibility: pnpm stamps a `prunedAt` wall-clock timestamp into
      # node_modules/.modules.yaml, so two installs of the identical store
      # differ by that one line. It is prune-scheduling metadata pnpm never
      # needs at runtime; drop it so the installed tree is byte-stable.
      if [ -f node_modules/.modules.yaml ]; then
        sed -i '/^prunedAt:/d' node_modules/.modules.yaml
      fi

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

{runtime_json}
    '';
  }};

in
{{
  package = app;

  env = {{{nix_env_attrs}}};
}}
"""
