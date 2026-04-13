# hop3.nix - Nix expression for Vikunja deployment
#
# Wraps the nixpkgs vikunja package (built from source by nixpkgs)
# with a startup wrapper that generates configuration and starts the server.

{ pkgs ? import <nixpkgs> {} }:

let
  vikunja = pkgs.vikunja;

  app = pkgs.stdenv.mkDerivation {
    pname = "vikunja";
    version = vikunja.version;
    meta = {
      description = "Open source task and project management";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      # Create wrapper script that configures vikunja via env vars.
      # Vikunja reads ``VIKUNJA_<section>_<key>`` env vars — this is
      # more robust than a generated YAML, since it avoids schema
      # drift between versions.
      cat > $out/bin/vikunja-wrapper << 'WRAPPER'
#!/bin/sh
set -e
PORT="''${PORT:-8080}"

mkdir -p files

# Service
export VIKUNJA_SERVICE_INTERFACE=":$PORT"
# Vikunja v2.x validates: if cors.enable is true (default), publicurl
# MUST be set — it's used as the CORS origin. The deprecated
# ``frontendurl`` alias no longer satisfies the check on its own.
export VIKUNJA_SERVICE_PUBLICURL="''${VIKUNJA_FRONTEND_URL:-http://localhost:$PORT/}"
export VIKUNJA_SERVICE_FRONTENDURL="$VIKUNJA_SERVICE_PUBLICURL"

# Generate and persist a JWT secret on first run (required in v2.x)
if [ ! -f .jwt-secret ]; then
  (tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null || openssl rand -base64 48) \
    | head -c 64 > .jwt-secret
fi
export VIKUNJA_SERVICE_JWTSECRET="$(cat .jwt-secret)"

# Database
export VIKUNJA_DATABASE_TYPE=postgres
export VIKUNJA_DATABASE_HOST="''${PGHOST:-localhost}"
export VIKUNJA_DATABASE_PORT="''${PGPORT:-5432}"
export VIKUNJA_DATABASE_DATABASE="''${PGDATABASE:-vikunja}"
export VIKUNJA_DATABASE_USER="''${PGUSER:-vikunja}"
export VIKUNJA_DATABASE_PASSWORD="''${PGPASSWORD:-}"

# Files
export VIKUNJA_FILES_BASEPATH="$PWD/files"

exec ${vikunja}/bin/vikunja
WRAPPER
      chmod +x $out/bin/vikunja-wrapper

      # Write runtime metadata for Hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/vikunja-wrapper"
  },
  "env": {
    "VIKUNJA_FRONTEND_URL": "http://localhost:8080/"
  },
  "path": [
    "$out/bin",
    "${vikunja}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;

  env = {
    VIKUNJA_FRONTEND_URL = "http://localhost:8080/";
  };
}
