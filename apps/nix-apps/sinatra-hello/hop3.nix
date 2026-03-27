# hop3.nix - Nix expression for Sinatra deployment
#
# This file defines how to build and run this Sinatra application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.

{ pkgs ? import <nixpkgs> {} }:

let
  ruby = pkgs.ruby_3_3;

  # Create a bundler environment with all gems from Gemfile.lock
  gems = pkgs.bundlerEnv {
    name = "sinatra-hello-gems";
    inherit ruby;
    gemdir = ./.;
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "sinatra-hello";
    version = "0.1.0";
    meta = {
      description = "Simple Sinatra hello world for Hop3 Nix integration";
    };

    src = ./.;

    buildInputs = [ ruby gems ];

    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin

      # Copy application files
      cp *.rb config.ru Gemfile Gemfile.lock $out/app/

      # Create wrapper script that uses the bundled puma
      cat > $out/bin/sinatra-hello << EOF
#!/bin/sh
cd $out/app
exec ${gems}/bin/puma -b "tcp://\''${BIND_ADDRESS:-127.0.0.1}:\''${PORT:-4567}" config.ru
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
    "${gems}/bin",
    "${ruby}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;
  env = {
    RACK_ENV = "production";
  };
}
