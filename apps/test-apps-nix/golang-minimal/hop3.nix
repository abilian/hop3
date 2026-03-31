# hop3.nix - Nix expression for minimal Go deployment
#
# This file defines how to build and run this Go application.
# Uses only the standard library (net/http).

{ pkgs ? import <nixpkgs> {} }:

let
  app = pkgs.buildGoModule {
    pname = "golang-minimal";
    version = "0.1.0";
    meta = {
      description = "Minimal Go hello world for Hop3 Nix integration";
    };

    src = ./.;

    # No external dependencies
    vendorHash = null;

    postInstall = ''
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/golang-minimal"
  },
  "env": {},
  "path": [
    "$out/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;
  env = {};
}
