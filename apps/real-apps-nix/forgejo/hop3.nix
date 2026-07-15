# hop3.nix - Nix expression for Forgejo deployment
#
# Wraps the nixpkgs forgejo package with a startup wrapper that
# generates the app.ini from env vars and starts the server.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  forgejo = pkgs.forgejo;

  app = pkgs.stdenv.mkDerivation {
    pname = "forgejo";
    version = forgejo.version;
    meta = {
      description = "Self-hosted Git service (Gitea fork)";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/forgejo-wrapper << 'WRAPPER'
      #!/bin/sh
      PORT="''${PORT:-8080}"
      DB_HOST="''${PGHOST:-localhost}"
      DB_PORT="''${PGPORT:-5432}"
      DB_NAME="''${PGDATABASE:-forgejo}"
      DB_USER="''${PGUSER:-forgejo}"
      DB_PASS="''${PGPASSWORD:-}"

      export GITEA_WORK_DIR="$PWD"

      mkdir -p custom/conf data

      cat > custom/conf/app.ini << EOF
      [server]
      HTTP_PORT = ''${PORT}
      ROOT_URL = http://localhost:''${PORT}/
      DISABLE_SSH = true

      [database]
      DB_TYPE = postgres
      HOST = ''${DB_HOST}:''${DB_PORT}
      NAME = ''${DB_NAME}
      USER = ''${DB_USER}
      PASSWD = ''${DB_PASS}

      [repository]
      ROOT = data/forgejo-repositories

      [log]
      MODE = console
      LEVEL = Info

      [security]
      INSTALL_LOCK = true
      SECRET_KEY = $(head -c 32 /dev/urandom | base64)
      EOF

      # nixpkgs installs forgejo's server binary as `gitea` (its generic.nix
      # renames forgejo.org -> gitea in preInstall; meta.mainProgram = "gitea").
      # There is no $out/bin/forgejo — exec'ing it exits 127 in a respawn loop.
      exec ${forgejo}/bin/gitea web
      WRAPPER
      chmod +x $out/bin/forgejo-wrapper

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": {
          "web": "$out/bin/forgejo-wrapper"
        },
        "env": {},
        "path": [
          "$out/bin",
          "${forgejo}/bin"
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
