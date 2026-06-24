# hop3.nix - Nix expression for GoToSocial deployment
#
# Wraps the nixpkgs gotosocial package. The binary lives at
# ${gotosocial}/bin/gotosocial; the web assets live at
# ${gotosocial}/share/gotosocial/web — we wire those into
# GTS_WEB_ASSET_BASE_DIR / GTS_WEB_TEMPLATE_BASE_DIR.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  gotosocial = pkgs.gotosocial;

  app = pkgs.stdenv.mkDerivation {
    pname = "gotosocial";
    version = gotosocial.version;
    meta = {
      description = "Lightweight ActivityPub-compatible microblog server";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/gotosocial-wrapper << 'WRAPPER'
      #!/bin/sh
      set -e

      mkdir -p storage

      export GTS_HOST="''${GTS_HOST:-localhost}"
      export GTS_BIND_ADDRESS="0.0.0.0"
      export GTS_PORT="''${PORT:-8080}"
      export GTS_DB_TYPE="''${GTS_DB_TYPE:-sqlite}"
      export GTS_DB_ADDRESS="''${GTS_DB_ADDRESS:-$PWD/storage/gotosocial.sqlite}"
      export GTS_STORAGE_LOCAL_BASE_PATH="''${GTS_STORAGE_LOCAL_BASE_PATH:-$PWD/storage}"
      export GTS_LETSENCRYPT_ENABLED="false"
      export GTS_WEB_ASSET_BASE_DIR="${gotosocial}/share/gotosocial/web/assets"
      export GTS_WEB_TEMPLATE_BASE_DIR="${gotosocial}/share/gotosocial/web/template"

      exec ${gotosocial}/bin/gotosocial --config-path "" server start
      WRAPPER
      chmod +x $out/bin/gotosocial-wrapper

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": {
          "web": "$out/bin/gotosocial-wrapper"
        },
        "env": {
          "GTS_BIND_ADDRESS": "0.0.0.0",
          "GTS_DB_TYPE": "sqlite",
          "GTS_LETSENCRYPT_ENABLED": "false"
        },
        "path": [
          "$out/bin",
          "${gotosocial}/bin"
        ]
      }
      EOF
    '';
  };

in
{
  package = app;

  env = {
    GTS_BIND_ADDRESS = "0.0.0.0";
    GTS_DB_TYPE = "sqlite";
    GTS_LETSENCRYPT_ENABLED = "false";
  };
}
