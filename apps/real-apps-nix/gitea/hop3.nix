# hop3.nix - Nix expression for Gitea deployment
#
# Downloads the pre-built Gitea binary and creates a wrapper
# that generates configuration and starts the server.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "1.21.4";

  gitea-bin = pkgs.fetchurl {
    url = "https://dl.gitea.io/gitea/${version}/gitea-${version}-linux-amd64";
    sha256 = "WKxZM2BGLQAAHisMlMhDoXF6pTFW8Pt30y5+V57jv6s=";
    executable = true;
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "gitea";
    inherit version;
    meta = {
      description = "Self-hosted Git service";
    };

    dontUnpack = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      # Install the binary
      cp ${gitea-bin} $out/bin/gitea
      chmod +x $out/bin/gitea

      # Create wrapper script that generates config and starts gitea
      cat > $out/bin/gitea-wrapper << 'WRAPPER'
#!/bin/sh
PORT="''${PORT:-8080}"
DB_HOST="''${PGHOST:-localhost}"
DB_PORT="''${PGPORT:-5432}"
DB_NAME="''${PGDATABASE:-gitea}"
DB_USER="''${PGUSER:-gitea}"
DB_PASS="''${PGPASSWORD:-}"

# Setup working directory structure
mkdir -p custom/conf data

# Generate configuration
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

exec BINDIR/gitea web
WRAPPER
      sed -i "s|BINDIR|$out/bin|g" $out/bin/gitea-wrapper
      chmod +x $out/bin/gitea-wrapper

      # Write runtime metadata for Hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/gitea-wrapper"
  },
  "env": {},
  "path": [
    "$out/bin"
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
