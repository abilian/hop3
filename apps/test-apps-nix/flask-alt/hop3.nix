# hop3.nix - Nix expression for Flask/Gunicorn deployment
#
# This file defines how to build and run this Flask application with Gunicorn.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.

{ pkgs ? import <nixpkgs> {} }:

let
  pythonEnv = pkgs.python3.withPackages (ps: with ps; [
    flask
    gunicorn
  ]);

  app = pkgs.stdenv.mkDerivation {
    pname = "flask-alt";
    version = "0.1.0";
    meta = {
      description = "Flask with Gunicorn for Hop3 Nix integration";
    };

    src = ./.;

    buildInputs = [ pythonEnv ];

    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp *.py $out/app/

      cat > $out/bin/flask-alt << EOF
#!/bin/sh
exec ${pythonEnv}/bin/gunicorn -b "\''${BIND_ADDRESS:-127.0.0.1}:\''${PORT:-8000}" app:app
EOF
      chmod +x $out/bin/flask-alt

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/flask-alt"
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
  };

in
{
  package = app;
  env = {
    FLASK_ENV = "production";
    PYTHONDONTWRITEBYTECODE = "1";
  };
}
