# hop3.nix - Nix expression for Focalboard deployment
#
# Downloads the pre-built Focalboard release and creates a wrapper
# that generates configuration and starts the server.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "7.10.5";

  focalboard-release = pkgs.fetchurl {
    url = "https://github.com/mattermost-community/focalboard/releases/download/v${version}/focalboard-server-linux-amd64.tar.gz";
    sha256 = "VZFQqC5QwR/gy6/RKtA55kuIUMer8hGYdZi9otDxiAQ=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "focalboard";
    inherit version;
    meta = {
      description = "Open source project management tool";
    };

    src = focalboard-release;
    sourceRoot = ".";

    unpackPhase = ''
      tar xzf $src
    '';

    installPhase = ''
      mkdir -p $out/bin $out/hop3 $out/share/focalboard

      # Install server binary and webapp assets
      cp -r focalboard/bin/focalboard-server $out/bin/
      cp -r focalboard/pack $out/share/focalboard/webapp-pack || true

      # Create wrapper script that generates config and starts focalboard
      cat > $out/bin/focalboard-wrapper << 'WRAPPER'
#!/bin/sh
PORT="''${PORT:-8080}"

mkdir -p files

cat > config.json << EOF
{
  "serverRoot": "http://localhost:''${PORT}",
  "port": ''${PORT},
  "dbtype": "postgres",
  "dbconfig": "postgres://''${PGUSER:-focalboard}:''${PGPASSWORD:-}@''${PGHOST:-localhost}:''${PGPORT:-5432}/''${PGDATABASE:-focalboard}?sslmode=disable",
  "postgres_dbconfig": "postgres://''${PGUSER:-focalboard}:''${PGPASSWORD:-}@''${PGHOST:-localhost}:''${PGPORT:-5432}/''${PGDATABASE:-focalboard}?sslmode=disable",
  "webpath": "SHAREDIR/webapp-pack",
  "filespath": "./files",
  "telemetry": false,
  "session_expire_time": 2592000,
  "session_refresh_time": 18000,
  "localOnly": false,
  "enableLocalMode": true,
  "localModeSocketLocation": "/var/tmp/focalboard_local.socket"
}
EOF

exec BINDIR/focalboard-server
WRAPPER
      sed -i "s|BINDIR|$out/bin|g" $out/bin/focalboard-wrapper
      sed -i "s|SHAREDIR|$out/share/focalboard|g" $out/bin/focalboard-wrapper
      chmod +x $out/bin/focalboard-wrapper

      # Write runtime metadata for Hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/focalboard-wrapper"
  },
  "env": {
    "FOCALBOARD_EDITION": "personal"
  },
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

  env = {
    FOCALBOARD_EDITION = "personal";
  };
}
