# hop3.nix - Nix expression for static site deployment
#
# This file defines a static website deployment.
# Hop3's NixBuilder will serve the built files via nginx.

{ pkgs ? import <nixpkgs> {} }:

let
  app = pkgs.stdenv.mkDerivation {
    pname = "static-hello";
    version = "0.1.0";
    meta.description = "Static hello world site for Hop3 Nix integration";

    src = ./.;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/public $out/hop3

      cp -r public/* $out/public/

      # Runtime metadata: static worker points nginx at the public dir
      cat > $out/hop3/runtime.json <<EOF
{
  "workers": {
    "static": "$out/public"
  },
  "env": {}
}
EOF
    '';
  };

in {
  package = app;
  env = {};
}
