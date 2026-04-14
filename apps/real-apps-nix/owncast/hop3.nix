# hop3.nix - Nix expression for Owncast deployment
#
# Owncast 0.2.x embeds its web assets into the Go binary via `embed`,
# so no sibling asset directory is required at runtime. The binary
# needs ffmpeg on PATH for transcoding; nixpkgs' owncast derivation
# typically wraps it with ffmpeg in the closure, so no extra wiring
# is needed here.

{ pkgs ? import <nixpkgs> {} }:

let
  owncast = pkgs.owncast;

  app = pkgs.stdenv.mkDerivation {
    pname = "owncast";
    version = owncast.version;
    meta = {
      description = "Self-hosted livestream server";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/owncast-wrapper << 'WRAPPER'
      #!/bin/sh
      set -e

      mkdir -p data

      exec ${owncast}/bin/owncast \
        --webserverport "''${PORT:-8080}" \
        --webserverip 0.0.0.0 \
        --database data/owncast.db
      WRAPPER
      chmod +x $out/bin/owncast-wrapper

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": {
          "web": "$out/bin/owncast-wrapper"
        },
        "env": {},
        "path": [
          "$out/bin",
          "${owncast}/bin",
          "${pkgs.ffmpeg}/bin"
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
