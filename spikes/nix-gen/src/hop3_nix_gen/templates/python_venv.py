"""python-venv template.

For Python applications that are not in nixpkgs and need to be installed
via pip. Creates a virtualenv in ``$out/venv`` and pip-installs the
specified packages. Requires ``__noChroot = true`` so the build can
access the network.

Example apps: Isso.
"""

from __future__ import annotations

from hop3_nix_gen.spec import AppSpec
from hop3_nix_gen.templates.base import (
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
)


class PythonVenvTemplate:
    name = "python-venv"

    def generate(self, spec: AppSpec) -> str:
        if not spec.pip_packages:
            raise ValueError("python-venv requires pip_packages")
        if spec.exec_target is None:
            raise ValueError("python-venv requires exec_target (e.g., 'isso')")
        runtime_package = spec.runtime_package or "python3"

        # python-venv doesn't fetch a source URL — it pip-installs
        # packages, so we skip source_nix entirely.

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"VENVBIN/{spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        pip_install_line = "$out/venv/bin/pip install " + " ".join(
            spec.pip_packages
        )

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'python-venv' by hop3-nix-gen.
# Run 'hop3 nix:eject {spec.pname}' to materialize for customization.

{{ pkgs ? import <nixpkgs> {{}} }}:

let
  version = "{spec.version}";
  python = pkgs.{runtime_package};

  app = pkgs.stdenv.mkDerivation {{
    # pip install needs network access during build
    __noChroot = true;

    pname = "{spec.pname}";
    inherit version;
    meta.description = "{spec.description}";

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ python pkgs.python3Packages.pip ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/venv $out/hop3

      # Create virtualenv and install packages
      ${{python}}/bin/python -m venv $out/venv
      {pip_install_line}

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|VENVBIN|$out/venv/bin|g" $out/bin/{spec.pname}
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
