# hop3.nix - Nix expression for Sinatra deployment
#
# This file defines how to build and run this Sinatra application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.

{ pkgs ? import <nixpkgs> {} }:

let
  # Ruby environment with dependencies
  ruby = pkgs.ruby_3_2;

  # Bundler for dependency management
  bundler = pkgs.bundler;

  # The application package
  app = pkgs.stdenv.mkDerivation {
    pname = "sinatra-hello";
    version = "0.1.0";
    meta = {
      description = "Simple Sinatra hello world for Hop3 Nix integration";
    };

    src = ./.;

    buildInputs = [ ruby bundler ];

    # No build phase needed
    dontBuild = true;

    installPhase = ''
      # Create output directories
      mkdir -p $out/app $out/bin

      # Copy application code
      cp -r *.rb *.ru Gemfile* $out/app/ 2>/dev/null || true
      cp *.rb $out/app/
      cp config.ru $out/app/
      cp Gemfile $out/app/

      # Create wrapper script that runs puma
      cat > $out/bin/sinatra-hello << EOF
#!/bin/sh
cd $out/app
exec ${ruby}/bin/ruby -S puma -b "tcp://\''${BIND_ADDRESS:-127.0.0.1}:\''${PORT:-4567}" config.ru
EOF
      chmod +x $out/bin/sinatra-hello

      # Write runtime metadata for Hop3
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/sinatra-hello"
  },
  "env": {
    "RACK_ENV": "production"
  },
  "path": [
    "$out/bin",
    "${ruby}/bin",
    "${bundler}/bin"
  ],
  "setup": "cd $out/app && ${bundler}/bin/bundle install --deployment --without development test"
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
    RACK_ENV = "production";
  };
}
