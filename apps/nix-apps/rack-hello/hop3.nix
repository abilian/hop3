# hop3.nix - Nix expression for Ruby Rack deployment
#
# This file defines how to build and run this Rack application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.

{ pkgs ? import <nixpkgs> {} }:

let
  ruby = pkgs.ruby_3_2;
  bundler = pkgs.bundler;

  app = pkgs.stdenv.mkDerivation {
    pname = "rack-hello";
    version = "0.1.0";
    meta = {
      description = "Simple Rack hello world for Hop3 Nix integration";
    };

    src = ./.;

    buildInputs = [ ruby bundler ];

    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp *.rb *.ru Gemfile* $out/app/ 2>/dev/null || true
      cp hello.rb config.ru Gemfile $out/app/

      cat > $out/bin/rack-hello << EOF
#!/bin/sh
cd $out/app
exec ${ruby}/bin/ruby -S rackup -o "\''${BIND_ADDRESS:-127.0.0.1}" -p "\''${PORT:-9292}" config.ru
EOF
      chmod +x $out/bin/rack-hello

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
  package = app;
  env = {
    RACK_ENV = "production";
  };
}
