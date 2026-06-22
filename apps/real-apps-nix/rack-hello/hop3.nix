# hop3.nix - Nix expression for Ruby Rack deployment
#
# This file defines how to build and run this Rack application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  ruby = pkgs.ruby_3_3;

  # Create a bundler environment with all gems from Gemfile.lock
  gems = pkgs.bundlerEnv {
    name = "rack-hello-gems";
    inherit ruby;
    gemdir = ./.;
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "rack-hello";
    version = "0.1.0";
    meta = {
      description = "Simple Rack hello world for Hop3 Nix integration";
    };

    src = ./.;

    buildInputs = [ ruby gems ];

    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin

      # Copy application files
      cp hello.rb config.ru Gemfile Gemfile.lock $out/app/

      # Create wrapper script that uses the bundled gems
      cat > $out/bin/rack-hello << EOF
#!/bin/sh
cd $out/app
exec ${gems}/bin/rackup -o "\''${BIND_ADDRESS:-127.0.0.1}" -p "\''${PORT:-9292}" config.ru
EOF
      chmod +x $out/bin/rack-hello

      # Write runtime metadata for Hop3
      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/rack-hello"
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
