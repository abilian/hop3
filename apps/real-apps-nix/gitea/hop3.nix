# hop3.nix - Nix expression for Gitea deployment
#
# Wraps the nixpkgs gitea package (built from source by nixpkgs)
# with a startup wrapper that generates config and starts the server.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  gitea = pkgs.gitea;

  app = pkgs.stdenv.mkDerivation {
    pname = "gitea";
    version = gitea.version;
    meta = {
      description = "Self-hosted Git service";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/gitea-wrapper << 'WRAPPER'
#!/bin/sh
PORT="''${PORT:-8080}"
DB_HOST="''${PGHOST:-localhost}"
DB_PORT="''${PGPORT:-5432}"
DB_NAME="''${PGDATABASE:-gitea}"
DB_USER="''${PGUSER:-gitea}"
DB_PASS="''${PGPASSWORD:-}"

# Set work dir to current directory (writable), not binary's parent
export GITEA_WORK_DIR="$PWD"

mkdir -p custom/conf data

cat > custom/conf/app.ini << EOF
[server]
HTTP_PORT = ''${PORT}
ROOT_URL = http://localhost:''${PORT}/

[database]
DB_TYPE = postgres
HOST = ''${DB_HOST}:''${DB_PORT}
NAME = ''${DB_NAME}
USER = ''${DB_USER}
PASSWD = ''${DB_PASS}

[repository]
ROOT = data/gitea-repositories

[log]
MODE = console
LEVEL = Info

[security]
INSTALL_LOCK = true
SECRET_KEY = $(head -c 32 /dev/urandom | base64)
EOF

exec ${gitea}/bin/gitea web
WRAPPER
      chmod +x $out/bin/gitea-wrapper

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/gitea-wrapper"
  },
  "env": {},
  "path": [
    "$out/bin",
    "${gitea}/bin"
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
