# hop3.nix - Nix expression for Gatus deployment
#
# Wraps the nixpkgs gatus package. Gatus reads config/config.yaml
# relative to CWD at startup; the wrapper generates a minimal config
# on first run.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  gatus = pkgs.gatus;

  app = pkgs.stdenv.mkDerivation {
    pname = "gatus";
    version = gatus.version;
    meta = {
      description = "Status pages and health-check monitoring";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/gatus-wrapper << 'WRAPPER'
      #!/bin/sh
      set -e

      mkdir -p config data

      PORT="''${PORT:-8080}"

      cat > config/config.yaml << EOF
      storage:
        type: sqlite
        path: data/gatus.db

      web:
        address: 0.0.0.0
        port: ''${PORT}

      endpoints:
        - name: self
          url: http://localhost:''${PORT}/health
          interval: 60s
          conditions:
            - "[STATUS] == 200"
      EOF

      exec ${gatus}/bin/gatus
      WRAPPER
      chmod +x $out/bin/gatus-wrapper

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": {
          "web": "$out/bin/gatus-wrapper"
        },
        "env": {},
        "path": [
          "$out/bin",
          "${gatus}/bin"
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
