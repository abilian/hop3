# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, TC001

"""go-source template.

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

from hop3.plugins.build.nix.gen.spec import AppSpec
from hop3.plugins.build.nix.gen.templates.base import (
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
    pinned_nixpkgs_header,
)

_NO_VENDOR_HASH = (
    "{pname}: go-source requires `go-vendor-hash` in [nix] — the sha256 of the "
    "vendored Go module set. Build once with a placeholder "
    '(`go-vendor-hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="`) '
    "and read the `got:` hash Nix reports, or run "
    "`hop3-tools nix vendor-hash <app-dir>`."
)


def _nix_string_list(values: list[str]) -> str:
    """Render a Python list as a Nix list of strings."""
    return " ".join(f'"{value}"' for value in values)


class GoSourceTemplate:
    name = "go-source"

    def generate(self, spec: AppSpec) -> str:
        if spec.exec_target is None:
            raise ValueError("go-source requires exec_target (the binary name)")
        if not spec.go_vendor_hash:
            raise ValueError(_NO_VENDOR_HASH.format(pname=spec.pname))

        binding = f"{spec.pname.replace('-', '_')}_src"
        source_nix = spec.source.as_nix(binding)

        optional_attrs = []
        if spec.source_root:
            optional_attrs.append(f'    sourceRoot = "{spec.source_root}";')
        if spec.go_sub_packages:
            packages = _nix_string_list(spec.go_sub_packages)
            optional_attrs.append(f"    subPackages = [ {packages} ];")
        if spec.go_ldflags:
            flags = _nix_string_list(spec.go_ldflags)
            optional_attrs.append(f"    ldflags = [ {flags} ];")
        optional_block = ("\n".join(optional_attrs) + "\n") if optional_attrs else ""

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"PKGBIN/{spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

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

  # Compiled here, not downloaded: a prebuilt binary cannot be audited, and a
  # nixpkgs wrapper would mean nixpkgs, not Hop3, packaged the application.
  goApp = pkgs.buildGoModule {{
    pname = "{spec.pname}";
    inherit version;
    src = {binding};

    # Pins the module set. `null` would let the build resolve modules from the
    # network, which is exactly what must not happen.
    vendorHash = "{spec.go_vendor_hash}";
{optional_block}
    # Upstream test suites frequently need network or a database; running them
    # here would make the build non-hermetic and flaky.
    doCheck = false;
  }};

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
      sed -i "s|PKGBIN|${{goApp}}/bin|g" $out/bin/{spec.pname}
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
