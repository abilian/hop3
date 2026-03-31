# hop3.nix - Nix expression for Miniflux deployment
#
# Downloads the pre-built Miniflux binary and creates a wrapper
# that configures it to use the PORT environment variable.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "2.1.1";

  miniflux-bin = pkgs.fetchurl {
    url = "https://github.com/miniflux/v2/releases/download/${version}/miniflux-linux-amd64";
    sha256 = "ydbOKn/voD05Hvl1wAU2GUcCccHimmB/2b0q+4RrKcU=";
    executable = true;
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "miniflux";
    inherit version;
    meta = {
      description = "Minimalist and opinionated RSS reader";
    };

    dontUnpack = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      # Install the binary
      cp ${miniflux-bin} $out/bin/miniflux
      chmod +x $out/bin/miniflux

      # Create wrapper script that sets up environment
      cat > $out/bin/miniflux-wrapper << 'WRAPPER'
#!/bin/sh
export LISTEN_ADDR="0.0.0.0:''${PORT:-8080}"
export RUN_MIGRATIONS=1
export CREATE_ADMIN=1
export ADMIN_USERNAME="''${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="''${ADMIN_PASSWORD:-changeme}"

# Construct DATABASE_URL from PG* env vars if not set
if [ -z "$DATABASE_URL" ]; then
  export DATABASE_URL="postgres://''${PGUSER:-miniflux}:''${PGPASSWORD:-}@''${PGHOST:-localhost}:''${PGPORT:-5432}/''${PGDATABASE:-miniflux}?sslmode=disable"
fi

exec BINDIR/miniflux
WRAPPER
      sed -i "s|BINDIR|$out/bin|g" $out/bin/miniflux-wrapper
      chmod +x $out/bin/miniflux-wrapper

      # Write runtime metadata for Hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/miniflux-wrapper"
  },
  "env": {
    "RUN_MIGRATIONS": "1",
    "CREATE_ADMIN": "1",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "changeme"
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
    RUN_MIGRATIONS = "1";
    CREATE_ADMIN = "1";
    ADMIN_USERNAME = "admin";
    ADMIN_PASSWORD = "changeme";
  };
}
