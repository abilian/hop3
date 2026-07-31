# hop3.nix - Nix expression for Vikunja deployment
#
# Wraps the nixpkgs vikunja package (built from source by nixpkgs)
# with a startup wrapper that generates configuration and starts the server.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

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

# A CONFIG FILE, not exports.
#
# These settings used to be `export VIKUNJA_*` in this wrapper, which meant only
# the server process ever saw them. `[admin].create` and `[probe].create` run
# OUTSIDE the wrapper, so `vikunja user create` found no database configuration
# — its own log says so on every run: "No config file found, using default or
# config from environment variables" — and fell back to Vikunja's defaults. The
# accounts were created somewhere other than the database the server reads,
# which is why a sign-in answered "Wrong username or password" for the admin.
#
# nixpkgs ships 0.24.6, the same version the template-generated variant builds
# from source, so the version was never the difference. The config file is.
cat > config.yml << CFGEOF
service:
  interface: ":$PORT"
  publicurl: "''${HOP3_PUBLIC_URL:-http://localhost:$PORT}/"
  frontendurl: "''${HOP3_PUBLIC_URL:-http://localhost:$PORT}/"
  jwtsecret: "$(cat .jwt-secret)"

cors:
  enable: false

database:
  type: postgres
  host: ''${PGHOST:-localhost}
  port: ''${PGPORT:-5432}
  database: ''${PGDATABASE:-vikunja}
  user: ''${PGUSER:-vikunja}
  password: ''${PGPASSWORD:-}

files:
  basepath: $PWD/files
CFGEOF

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
    "VIKUNJA_DATABASE_TYPE": "postgres",
    "VIKUNJA_FILES_BASEPATH": "files"
  },
  "path": [
    "$out/bin",
    "${vikunja}/bin",
    "${pkgs.postgresql}/bin"
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
