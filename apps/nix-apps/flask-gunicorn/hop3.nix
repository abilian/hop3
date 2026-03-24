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
    pname = "flask-gunicorn";
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

      cat > $out/bin/flask-gunicorn << 'EOF'
#!/bin/sh
exec ${pythonEnv}/bin/python -m gunicorn app:app "$@"
EOF
      chmod +x $out/bin/flask-gunicorn

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/flask-gunicorn --bind \$BIND_ADDRESS:\$PORT --chdir $out/app"
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
