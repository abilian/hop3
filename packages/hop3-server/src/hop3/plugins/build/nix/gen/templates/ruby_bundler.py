# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, TC001

"""ruby-bundler template.

For Ruby applications using Bundler for dependency management. Uses
``pkgs.bundlerEnv`` to create a Nix environment with all gems resolved
from the Gemfile.lock, then wraps the app with a startup script.

Requires the app source to contain ``Gemfile`` and ``Gemfile.lock``.
The generated hop3.nix must be written to the source directory (not a
temp dir) so that ``gemdir = ./.;`` resolves correctly.

Example apps: sinatra-hello, rack-hello.
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


class RubyBundlerTemplate:
    name = "ruby-bundler"

    def generate(self, spec: AppSpec) -> str:
        if spec.exec_target is None:
            raise ValueError("ruby-bundler requires exec_target")

        ruby_pkg = spec.runtime_package or "ruby_3_3"

        # Which app files to copy (defaults to common Ruby files)
        app_files = (
            " ".join(spec.exec_args)
            if spec.exec_args
            else "*.rb config.ru Gemfile Gemfile.lock"
        )

        exec_line = f"GEMSBIN/{spec.exec_target}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'ruby-bundler' by hop3-nix-gen.
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{PINNED_NIXPKGS_HEADER}

let
  ruby = pkgs.{ruby_pkg};

  gems = pkgs.bundlerEnv {{
    name = "{spec.pname}-gems";
    inherit ruby;
    gemdir = ./.;
  }};

  app = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}";
    version = "{spec.version}";
    meta = {{
      description = "{spec.description}";
    }};

    src = ./.;

    buildInputs = [ ruby gems ];

    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3

      # Copy application files
      cp {app_files} $out/app/ 2>/dev/null || true

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|GEMSBIN|${{gems}}/bin|g" $out/bin/{spec.pname}
      sed -i "s|APPDIR|$out/app|g" $out/bin/{spec.pname}
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
