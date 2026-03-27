# hop3.nix - Nix expression for static site deployment
#
# This file defines a static website deployment.
# Hop3's NixBuilder will serve the built files via nginx.

{ pkgs ? import <nixpkgs> {} }:

let
  # The static site package
  app = pkgs.stdenv.mkDerivation {
    pname = "static-hello";
    version = "0.1.0";
    meta = {
      description = "Static hello world site for Hop3 Nix integration";
    };

    src = ./.;

    # No build phase needed for static files
    dontBuild = true;

    installPhase = ''
      # Create output directory and copy static files
      mkdir -p $out/public
      cp -r public/* $out/public/

      # Write runtime metadata for Hop3
      # For static sites, we use the "static" worker type
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "static": "$out/public"
  },
  "env": {}
}
EOF
    '';
  };

in
{
  # Required: the package derivation
  package = app;

  # No environment variables needed for static sites
  env = {};
}
