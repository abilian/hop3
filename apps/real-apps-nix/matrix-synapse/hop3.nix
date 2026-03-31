# hop3.nix - Nix expression for Matrix Synapse deployment
#
# matrix-synapse is available as a top-level nixpkgs package.
# NOTE: This package is Linux-only in nixpkgs (will fail on macOS).

{ pkgs ? import <nixpkgs> {} }:

let
  synapse = pkgs.matrix-synapse;

  app = pkgs.stdenv.mkDerivation {
    pname = "matrix-synapse";
    version = synapse.version;
    meta.description = "Matrix homeserver implementation";

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/synapse-start << 'WRAPPER'
#!/bin/sh
mkdir -p data media_store
exec SYNAPSE_BIN \
  --server-name "''${SERVER_NAME:-localhost}" \
  --config-path homeserver.yaml \
  "$@"
WRAPPER
      sed -i "s|SYNAPSE_BIN|${synapse}/bin/synapse_homeserver|g" $out/bin/synapse-start
      chmod +x $out/bin/synapse-start

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/synapse-start"
  },
  "env": {
    "SERVER_NAME": "localhost"
  },
  "path": ["$out/bin", "${synapse}/bin"]
}
EOF
    '';
  };

in { package = app; }
