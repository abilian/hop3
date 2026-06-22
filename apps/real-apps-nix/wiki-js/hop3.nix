# hop3.nix - Nix expression for Wiki.js deployment
#
# Wraps the nixpkgs wiki-js package (built from source by nixpkgs)
# with a startup wrapper that generates config.yml and starts the server.
#
# Note: pkgs.wiki-js does NOT provide a bin/wiki-js — it's the raw
# source tree (server/, node_modules/, package.json). Wiki.js is started
# with `node server` from a writable directory containing config.yml.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  wiki-js = pkgs.wiki-js;
  nodejs = pkgs.nodejs;

  app = pkgs.stdenv.mkDerivation {
    pname = "wiki-js";
    version = wiki-js.version;
    meta = {
      description = "Modern and powerful wiki platform";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/wiki-js-wrapper << 'WRAPPER'
#!/bin/sh
export NODE_ENV=production

PORT="''${PORT:-8080}"
DB_HOST="''${PGHOST:-localhost}"
DB_PORT="''${PGPORT:-5432}"
DB_NAME="''${PGDATABASE:-wikijs}"
DB_USER="''${PGUSER:-wikijs}"
DB_PASS="''${PGPASSWORD:-}"

mkdir -p data

cat > config.yml << EOF
port: ''${PORT}
bindIP: 0.0.0.0

db:
  type: postgres
  host: ''${DB_HOST}
  port: ''${DB_PORT}
  user: ''${DB_USER}
  pass: ''${DB_PASS}
  db: ''${DB_NAME}
  ssl: false

logLevel: info

offline: false
ha: false

dataPath: ./data
EOF

# Symlink Wiki.js source tree from the nixpkgs store into cwd.
# Wiki.js's `node server` requires being run from a directory that
# contains config.yml AND the server/, node_modules/ tree alongside.
for item in server node_modules assets package.json; do
  if [ -e ${wiki-js}/$item ] && [ ! -e $item ]; then
    ln -sf ${wiki-js}/$item $item
  fi
done

exec ${nodejs}/bin/node server
WRAPPER
      chmod +x $out/bin/wiki-js-wrapper

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/wiki-js-wrapper"
  },
  "env": {
    "NODE_ENV": "production"
  },
  "path": [
    "$out/bin",
    "${nodejs}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;

  env = {
    NODE_ENV = "production";
  };
}
