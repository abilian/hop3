# hop3.nix - Nix expression for Stirling-PDF deployment
#
# Wraps the nixpkgs stirling-pdf package (Java/Spring Boot fat JAR)
# with a startup wrapper that configures it for Hop3.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  stirling-pdf = pkgs.stirling-pdf;

  app = pkgs.stdenv.mkDerivation {
    pname = "stirling-pdf";
    version = stirling-pdf.version;
    meta = {
      description = "Local web PDF toolkit";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/stirling-pdf-wrapper << 'WRAPPER'
      #!/bin/sh
      set -e

      mkdir -p configs customFiles logs pipeline

      export SERVER_PORT="''${PORT:-8080}"
      export SERVER_ADDRESS="0.0.0.0"
      export DOCKER_ENABLE_SECURITY="''${DOCKER_ENABLE_SECURITY:-false}"
      export SYSTEM_DEFAULTLOCALE="''${SYSTEM_DEFAULTLOCALE:-en-US}"

      exec ${stirling-pdf}/bin/Stirling-PDF
      WRAPPER
      chmod +x $out/bin/stirling-pdf-wrapper

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": {
          "web": "$out/bin/stirling-pdf-wrapper"
        },
        "env": {
          "SERVER_ADDRESS": "0.0.0.0",
          "DOCKER_ENABLE_SECURITY": "false",
          "SYSTEM_DEFAULTLOCALE": "en-US"
        },
        "path": [
          "$out/bin",
          "${stirling-pdf}/bin"
        ]
      }
      EOF
    '';
  };

in
{
  package = app;

  env = {
    SERVER_ADDRESS = "0.0.0.0";
    DOCKER_ENABLE_SECURITY = "false";
    SYSTEM_DEFAULTLOCALE = "en-US";
  };
}
