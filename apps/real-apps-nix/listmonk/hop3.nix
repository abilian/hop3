# hop3.nix - Nix expression for Listmonk deployment
#
# Downloads the pre-built Listmonk binary and creates a wrapper
# that generates configuration, initializes the database, and starts the server.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "3.0.0";

  listmonk-release = pkgs.fetchurl {
    url = "https://github.com/knadh/listmonk/releases/download/v${version}/listmonk_${version}_linux_amd64.tar.gz";
    sha256 = "KcSWUUYjHUD7m9Luy0aVNKZpJiwCVTh4ilbV02U5LPQ=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "listmonk";
    inherit version;
    meta = {
      description = "Self-hosted newsletter and mailing list manager";
    };

    src = listmonk-release;
    sourceRoot = ".";

    unpackPhase = ''
      tar xzf $src
    '';

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      # Install the binary
      cp listmonk $out/bin/listmonk
      chmod +x $out/bin/listmonk

      # Create wrapper script that generates config and starts listmonk
      cat > $out/bin/listmonk-wrapper << 'WRAPPER'
#!/bin/sh
PORT="''${PORT:-8080}"

cat > config.toml << EOF
[app]
address = "0.0.0.0:''${PORT}"
admin_username = "admin"
admin_password = "changeme"

[db]
host = "''${PGHOST:-localhost}"
port = ''${PGPORT:-5432}
user = "''${PGUSER:-listmonk}"
password = "''${PGPASSWORD:-}"
database = "''${PGDATABASE:-listmonk}"
ssl_mode = "disable"
max_open = 25
max_idle = 25
max_lifetime = "300s"
EOF

# Initialize database if needed
BINDIR/listmonk --install --yes 2>/dev/null || true

exec BINDIR/listmonk
WRAPPER
      sed -i "s|BINDIR|$out/bin|g" $out/bin/listmonk-wrapper
      chmod +x $out/bin/listmonk-wrapper

      # Write runtime metadata for Hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/listmonk-wrapper"
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
