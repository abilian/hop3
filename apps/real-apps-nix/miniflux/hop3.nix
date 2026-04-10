# hop3.nix - Nix expression for Miniflux deployment
#
# Wraps the nixpkgs miniflux package (built from source by nixpkgs)
# with a startup wrapper that configures it for Hop3.

{ pkgs ? import <nixpkgs> {} }:

let
  miniflux = pkgs.miniflux;

  app = pkgs.stdenv.mkDerivation {
    pname = "miniflux";
    version = miniflux.version;
    meta = {
      description = "Minimalist and opinionated RSS reader";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      # Wrapper that sets up environment and execs the nixpkgs binary
      cat > $out/bin/miniflux-wrapper << 'WRAPPER'
#!/bin/sh
export LISTEN_ADDR="0.0.0.0:''${PORT:-8080}"
export RUN_MIGRATIONS=1
export CREATE_ADMIN=1
export ADMIN_USERNAME="''${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="''${ADMIN_PASSWORD:-changeme}"

if [ -z "$DATABASE_URL" ]; then
  export DATABASE_URL="postgres://''${PGUSER:-miniflux}:''${PGPASSWORD:-}@''${PGHOST:-localhost}:''${PGPORT:-5432}/''${PGDATABASE:-miniflux}?sslmode=disable"
fi

exec ${miniflux}/bin/miniflux
WRAPPER
      chmod +x $out/bin/miniflux-wrapper

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
    "$out/bin",
    "${miniflux}/bin"
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
