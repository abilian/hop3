# hop3.nix - Nix expression for Hop3 deployment
#
# This file defines how to build and run this Flask application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.
#
# The format uses a two-phase approach:
# 1. Build phase: nix-build hop3.nix -A package
# 2. Runtime config: evaluated after build with store path substitution

{ pkgs ? import <nixpkgs> {} }:

let
  # Python environment with dependencies
  pythonEnv = pkgs.python3.withPackages (ps: with ps; [
    flask
    gunicorn
  ]);

  # The application package
  app = pkgs.stdenv.mkDerivation {
    pname = "flask-hello";
    version = "0.1.0";

    src = ./.;

    buildInputs = [ pythonEnv ];

    # No build phase needed for pure Python
    dontBuild = true;

    installPhase = ''
      # Create output directories
      mkdir -p $out/app $out/bin

      # Copy application code
      cp -r *.py $out/app/

      # Create wrapper script that sets up the environment
      cat > $out/bin/flask-hello << 'EOF'
#!/bin/sh
exec ${pythonEnv}/bin/python -m gunicorn app:app "$@"
EOF
      chmod +x $out/bin/flask-hello

      # Write runtime metadata for Hop3 to read after build
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/flask-hello --bind unix:\$HOP3_SOCKET --chdir $out/app"
  },
  "env": {
    "FLASK_ENV": "production",
    "PYTHONDONTWRITEBYTECODE": "1"
  },
  "path": [
    "$out/bin",
    "${pythonEnv}/bin"
  ]
}
EOF
    '';

    meta = {
      description = "Simple Flask hello world for Hop3 Nix integration";
    };
  };

in
{
  # Required: the package derivation
  package = app;

  # Static environment variables (no derivation references)
  env = {
    FLASK_ENV = "production";
    PYTHONDONTWRITEBYTECODE = "1";
  };
}
