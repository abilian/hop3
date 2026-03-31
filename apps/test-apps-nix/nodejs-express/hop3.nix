# hop3.nix - Nix expression for Node.js/Express deployment
#
# This file defines how to build and run this Express application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.

{ pkgs ? import <nixpkgs> {} }:

let
  # Node.js environment
  nodejs = pkgs.nodejs;

  # The application package using buildNpmPackage for proper dependency handling
  app = pkgs.buildNpmPackage {
    pname = "nodejs-express";
    version = "0.1.0";
    meta = {
      description = "Simple Express hello world for Hop3 Nix integration";
    };

    src = ./.;

    # Hash of npm dependencies (computed from package-lock.json)
    npmDepsHash = "sha256-p2oD6vN2wAAj7nHFBHl4KRUG+YlW2Nj4oLUDnZgSfrM=";

    # Don't run npm build (no build script in package.json)
    dontNpmBuild = true;

    installPhase = ''
      runHook preInstall

      # Create output directories
      mkdir -p $out/app $out/bin

      # Copy application code and node_modules
      cp -r *.js package.json $out/app/
      cp -r node_modules $out/app/

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
  ]
}
EOF

      runHook postInstall
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
