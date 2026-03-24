# hop3.nix - Nix expression for Node.js/Express deployment
#
# This file defines how to build and run this Express application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.

{ pkgs ? import <nixpkgs> {} }:

let
  # Node.js environment
  nodejs = pkgs.nodejs_20;

  # The application package
  app = pkgs.stdenv.mkDerivation {
    pname = "nodejs-express";
    version = "0.1.0";
    meta = {
      description = "Simple Express hello world for Hop3 Nix integration";
    };

    src = ./.;

    buildInputs = [ nodejs ];

    # No build phase needed - dependencies handled at runtime
    dontBuild = true;

    installPhase = ''
      # Create output directories
      mkdir -p $out/app $out/bin

      # Copy application code
      cp -r *.js $out/app/

      # Create package.json for runtime
      cat > $out/app/package.json << 'PACKAGE'
{
  "name": "nodejs-express-nix",
  "version": "0.1.0",
  "main": "app.js",
  "dependencies": {
    "express": "^4.18.2"
  }
}
PACKAGE

      # Create wrapper script
      cat > $out/bin/nodejs-express << EOF
#!/bin/sh
cd $out/app
exec ${nodejs}/bin/node app.js "\$@"
EOF
      chmod +x $out/bin/nodejs-express

      # Write runtime metadata for Hop3
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/nodejs-express"
  },
  "env": {
    "NODE_ENV": "production"
  },
  "path": [
    "$out/bin",
    "${nodejs}/bin"
  ],
  "setup": "cd $out/app && ${nodejs}/bin/npm install --production"
}
EOF
    '';
  };

in
{
  # Required: the package derivation
  package = app;

  # Environment variables
  env = {
    NODE_ENV = "production";
  };
}
