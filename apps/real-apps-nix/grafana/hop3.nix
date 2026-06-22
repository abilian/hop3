# hop3.nix - Nix expression for Grafana deployment
#
# Wraps the nixpkgs grafana package (built from source by nixpkgs)
# with a startup wrapper that generates configuration and starts the server.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  grafana = pkgs.grafana;

  app = pkgs.stdenv.mkDerivation {
    pname = "grafana";
    version = grafana.version;
    meta = {
      description = "The open and composable observability and data visualization platform";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      # Create wrapper script that generates config and starts grafana
      cat > $out/bin/grafana-wrapper << 'WRAPPER'
#!/bin/sh
PORT="''${PORT:-8080}"
DB_HOST="''${PGHOST:-localhost}"
DB_PORT="''${PGPORT:-5432}"
DB_NAME="''${PGDATABASE:-grafana}"
DB_USER="''${PGUSER:-grafana}"
DB_PASS="''${PGPASSWORD:-}"

mkdir -p data logs conf/provisioning/datasources conf/provisioning/dashboards

# Generate config with PostgreSQL backend
cat > conf/custom.ini << EOF
[server]
http_port = ''${PORT}

[paths]
data = data
logs = logs

[database]
type = postgres
host = ''${DB_HOST}:''${DB_PORT}
name = ''${DB_NAME}
user = ''${DB_USER}
password = ''${DB_PASS}
ssl_mode = disable

[security]
admin_user = ''${GF_SECURITY_ADMIN_USER:-admin}
EOF

export GF_SERVER_HTTP_PORT="''${PORT}"
export GF_PATHS_DATA="$PWD/data"
export GF_PATHS_LOGS="$PWD/logs"
export GF_PATHS_PROVISIONING="$PWD/conf/provisioning"

exec ${grafana}/bin/grafana server \
  --homepath ${grafana}/share/grafana \
  --config "$PWD/conf/custom.ini"
WRAPPER
      chmod +x $out/bin/grafana-wrapper

      # Write runtime metadata for Hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/grafana-wrapper"
  },
  "env": {
    "GF_SECURITY_ADMIN_USER": "admin",
    "GF_PATHS_DATA": "./data",
    "GF_PATHS_LOGS": "./logs"
  },
  "path": [
    "$out/bin",
    "${grafana}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;

  env = {
    GF_SECURITY_ADMIN_USER = "admin";
    GF_PATHS_DATA = "./data";
    GF_PATHS_LOGS = "./logs";
  };
}
