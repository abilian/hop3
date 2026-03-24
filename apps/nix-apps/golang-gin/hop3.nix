# hop3.nix - Nix expression for Go/Gin deployment
#
# This file defines how to build and run this Gin application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.

{ pkgs ? import <nixpkgs> {} }:

let
  # The application package - built using buildGoModule
  app = pkgs.buildGoModule {
    pname = "golang-gin";
    version = "0.1.0";
    meta = {
      description = "Simple Gin hello world for Hop3 Nix integration";
    };

    src = ./.;

    # Use vendorHash = null for simple cases, or compute the hash
    # For a real app, run: nix-prefetch-url --unpack <url>
    vendorHash = null;

    # Allow network access during build for dependency fetching
    # In production, you'd use a proper vendorHash
    proxyVendor = true;

    postInstall = ''
      # Rename binary to match app name
      mv $out/bin/golang-gin $out/bin/golang-gin-server || true

      # Write runtime metadata for Hop3
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/golang-gin-server"
  },
  "env": {
    "GIN_MODE": "release"
  },
  "path": [
    "$out/bin"
  ]
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
    GIN_MODE = "release";
  };
}
