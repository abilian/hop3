# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, raw-string-in-exception]


"""
go-source template.

Builds a Go application **from source** with ``buildGoModule``, then wraps the
resulting binary with Hop3's runtime metadata.

This is the compiled-language counterpart to ``php-app`` and ``python-venv``:
the two alternatives it replaces are both unacceptable for a reproducible,
auditable deployment.

- ``prebuilt-binary`` downloads an already-compiled artefact, so nothing about
  the build is verifiable and the binary is taken on trust.
- ``nixpkgs-wrapper`` is reproducible, but nixpkgs did the packaging; the
  application is not built by Hop3 at all.

``buildGoModule`` gives both properties at once. The module set is fixed by
``go.sum`` (a hash per module) and by ``vendorHash`` (the resolved set as a
whole), and the compile runs offline inside the sandbox — so the build is
hermetic and the result is Tier-1 reproducible.

Example apps: Gitea, Forgejo, Miniflux, Vikunja, Gatus.
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec, GoSourcePayload
from hop3.plugins.build.nix.gen.templates.base import (
    ReproTier,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
    pinned_nixpkgs_header,
)

# A module with no `require` block has nothing to vendor, and `vendorHash = null`
# is then the correct value rather than a missing one. Spelling it explicitly
# keeps the guard meaningful: an app with dependencies still cannot omit a hash.
NO_DEPENDENCIES = "none"

_NO_VENDOR_HASH = (
    "{pname}: go-source requires `go-vendor-hash` in [nix] — the sha256 of the "
    "vendored Go module set. Build once with a placeholder "
    '(`go-vendor-hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="`) '
    "and read the `got:` hash Nix reports, or run "
    "`hop3-tools nix vendor-hash <app-dir>`."
)

_NO_NPM_HASH = (
    "{pname}: go-source with `go-frontend-build` also needs `go-npm-deps-hash` "
    "in [nix] — the npmDepsHash pinning the frontend's npm set. Build once with "
    'a placeholder (`go-npm-deps-hash = "sha256-AAAA…="`) and read the `got:` '
    "hash Nix reports."
)

_NO_PNPM_HASH = (
    "{pname}: go-source with `go-frontend-pnpm` needs `go-pnpm-deps-hash` in "
    "[nix] — the pnpm.fetchDeps hash pinning the frontend's pnpm set. Build once "
    'with a placeholder (`go-pnpm-deps-hash = "sha256-AAAA…="`) and read the '
    "`got:` hash Nix reports."
)


def _nix_string_list(values: list[str]) -> str:
    """Render a Python list as a Nix list of strings."""
    return " ".join(f'"{value}"' for value in values)


def _frontend_block(
    spec: AppSpec, p: GoSourcePayload, binding: str, wrapper_body: str
) -> tuple[str, str, str, str]:
    """
    The optional JS-frontend derivation and its integration.

    Returns ``(frontend_nix, frontend_sed, frontend_prebuild, wrapper_body)``:
    the ``frontend`` let-binding, the wrapper sed (disk mode), the buildGoModule
    preBuild (embed mode), and the (possibly-updated) wrapper body. Two axes:
    npm (buildNpmPackage) vs pnpm (pnpm.fetchDeps + configHook), and disk-served
    (``$HOP3_GO_FRONTEND`` + a static-root config) vs embedded (``go:embed``,
    copied into the source before the compile).
    """
    if not p.frontend_build:
        return "", "", "", wrapper_body

    fe_root = (
        f'\n    sourceRoot = "{p.frontend_source_root}";'
        if p.frontend_source_root
        else ""
    )
    embed = p.frontend_embed_path
    # Embed mode makes $out the built-assets *contents* (so a single
    # `cp -r ${frontend} <path>` lands them where `go:embed` expects); disk
    # mode nests them under `$out/<output>/` for the static-root.
    fe_install = (
        f"cp -r {p.frontend_output} $out"
        if embed
        else f"mkdir -p $out\n      cp -R {p.frontend_output} $out/"
    )
    # Some Go apps resolve more than the built frontend under their static root.
    # gitea/forgejo look up BOTH `public/` and `options/` (locales, gitignores,
    # licences, label templates) there; shipping only the built frontend leaves
    # the locales missing, and gitea dies at boot registering a cron task
    # ("translation is missing for task ..."), crash-looping rather than
    # timing out. These directories come from the source tree, not the build.
    if p.static_dirs:
        copies = "\n      ".join(f"cp -R {d} $out/" for d in p.static_dirs)
        fe_install += f"\n      {copies}"

    if p.frontend_pnpm:
        if not p.pnpm_deps_hash:
            raise ValueError(_NO_PNPM_HASH.format(pname=spec.pname))
        sr_inherit = " sourceRoot" if p.frontend_source_root else ""
        # Emitted only when the recipe asks for it: the default nixpkgs pin's
        # fetcher rejects the argument outright.
        fetcher_version = (
            f"\n      fetcherVersion = {p.pnpm_fetcher_version};"
            if p.pnpm_fetcher_version is not None
            else ""
        )
        frontend_nix = f"""
  # The JS frontend, built offline with pnpm; pnpm.fetchDeps pins the dep set.
  frontend = pkgs.stdenv.mkDerivation (finalAttrs: {{
    pname = "{spec.pname}-frontend";
    inherit version;
    src = {binding};{fe_root}
    pnpmDeps = pkgs.{p.pnpm_package}.fetchDeps {{
      inherit (finalAttrs) pname version src{sr_inherit};
      hash = "{p.pnpm_deps_hash}";{fetcher_version}
    }};
    nativeBuildInputs =
      [ pkgs.{p.frontend_node_package} pkgs.{p.pnpm_package}.configHook ];
    buildPhase = ''{p.frontend_build}'';
    installPhase = ''
      {fe_install}
    '';
  }});
"""
    else:
        if not p.npm_deps_hash:
            raise ValueError(_NO_NPM_HASH.format(pname=spec.pname))
        frontend_nix = f"""
  # The JS frontend, built offline in its own derivation; npmDepsHash pins the
  # npm set (the vendorHash analogue for npm). The build command sets
  # BROWSERSLIST_IGNORE_OLD_DATA so browserslist doesn't embed a timestamped
  # cache — the classic webpack non-determinism.
  frontend = pkgs.buildNpmPackage {{
    pname = "{spec.pname}-frontend";
    inherit version;
    src = {binding};{fe_root}
    npmDepsHash = "{p.npm_deps_hash}";
    dontNpmBuild = true;
    buildPhase = ''{p.frontend_build}'';
    installPhase = ''
      {fe_install}
    '';
  }};
"""

    if embed:
        # Embedded (`go:embed`): copy the built assets into the source tree
        # before the Go compile; no runtime wiring needed.
        prebuild = f"\n    preBuild = ''\n      cp -r ${{frontend}} {embed}\n    '';"
        return frontend_nix, "", prebuild, wrapper_body

    # Disk-served: expose the assets to the wrapper; the recipe points the app's
    # static-root config at $HOP3_GO_FRONTEND.
    shebang, _, rest = wrapper_body.partition("\n")
    wrapper_body = shebang + '\nexport HOP3_GO_FRONTEND="FRONTENDDIR"\n' + rest
    sed = f'\n      sed -i "s|FRONTENDDIR|${{frontend}}|g" $out/bin/{spec.pname}'
    return frontend_nix, sed, "", wrapper_body


class GoSourceTemplate:
    name = "go-source"
    tier = ReproTier.SOURCE

    def generate(self, spec: AppSpec) -> str:
        p = spec.payload_as(GoSourcePayload)
        if spec.exec_target is None:
            raise ValueError("go-source requires exec_target (the binary name)")
        if not p.vendor_hash:
            raise ValueError(_NO_VENDOR_HASH.format(pname=spec.pname))

        # No `url` means the application *is* the recipe directory — a user's own
        # code pushed to Hop3, rather than third-party software fetched from
        # elsewhere. Without this the nix path is reachable only for software
        # someone else publishes, which is not the case a PaaS exists for.
        binding = f"{spec.pname.replace('-', '_')}_src"
        if spec.source.url:
            source_nix = spec.source.as_nix(binding)
            src_attr = binding
        else:
            source_nix = ""
            src_attr = "./."

        vendor_attr = (
            "null" if p.vendor_hash == NO_DEPENDENCIES else f'"{p.vendor_hash}"'
        )

        optional_attrs = []
        if spec.source_root:
            optional_attrs.append(f'    sourceRoot = "{spec.source_root}";')
        if p.proxy_vendor:
            optional_attrs.append("    proxyVendor = true;")
        if p.sub_packages:
            packages = _nix_string_list(p.sub_packages)
            optional_attrs.append(f"    subPackages = [ {packages} ];")
        if p.ldflags:
            flags = _nix_string_list(p.ldflags)
            optional_attrs.append(f"    ldflags = [ {flags} ];")
        optional_block = ("\n".join(optional_attrs) + "\n") if optional_attrs else ""

        # buildGoModule uses nixpkgs' default Go; override it for an app whose
        # go.mod needs a newer toolchain than the pinned default.
        go_builder = (
            f"(pkgs.buildGoModule.override {{ go = pkgs.{p.go_version}; }})"
            if p.go_version
            else "pkgs.buildGoModule"
        )

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"PKGBIN/{spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        frontend_nix, frontend_sed, frontend_prebuild, wrapper_body = _frontend_block(
            spec, p, src_attr, wrapper_body
        )

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'go-source' by hop3-nix-gen.
# Compiled from source with buildGoModule: go.sum hashes every module and
# vendorHash pins the resolved set, so the build is hermetic and offline.
#
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{pinned_nixpkgs_header(spec.nixpkgs_rev, spec.nixpkgs_sha256)}

let
  version = "{spec.version}";

{source_nix}
{frontend_nix}
  # Compiled here, not downloaded: a prebuilt binary cannot be audited, and a
  # nixpkgs wrapper would mean nixpkgs, not Hop3, packaged the application.
  goApp = {go_builder} {{
    pname = "{spec.pname}";
    inherit version;
    src = {src_attr};{frontend_prebuild}

    # Pins the module set. An unset hash would let the build resolve modules
    # from the network, which is exactly what must not happen; `null` is correct
    # only for a module that requires nothing (go-vendor-hash = "none").
    vendorHash = {vendor_attr};
{optional_block}
    # Upstream test suites frequently need network or a database; running them
    # here would make the build non-hermetic and flaky.
    doCheck = false;
  }};

  # The application itself, under the name every template exposes.
  #
  # `app` below is the WRAPPER derivation: its bin holds a generated script that
  # execs one fixed subcommand, so it is useless for anything else. An app's own
  # CLI lives here — and a recipe needs it, because [admin].create runs with the
  # runtime PATH and has no other way to reach the binary. gitea-nixgen's
  # bootstrap failed with `gitea: not found` while the binary sat in this
  # derivation, one store path away and not on PATH.
  pkg = goApp;

  app = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}";
    inherit version;
    meta.description = "{spec.description}";

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      # buildGoModule names each binary after its package directory, which for a
      # root main package is the last element of the module path — not the
      # application name. forgejo's `module forgejo.org` yields `bin/forgejo.org`
      # while gitea's `code.gitea.io/gitea` yields `bin/gitea`, so the two look
      # alike and behave differently. Catch the mismatch here: otherwise the
      # wrapper execs a path that does not exist, uWSGI crash-loops, and the
      # deploy reports a health-check timeout that names nothing useful.
      if [ ! -x ${{goApp}}/bin/{spec.exec_target} ]; then
        echo "exec-target '{spec.exec_target}' is not a binary in ${{goApp}}/bin." >&2
        echo "buildGoModule produced:" >&2
        ls -1 ${{goApp}}/bin >&2
        echo "Set [nix].exec-target to one of those names." >&2
        exit 1
      fi

      mkdir -p $out/bin $out/hop3

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|PKGBIN|${{goApp}}/bin|g" $out/bin/{spec.pname}{frontend_sed}
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
