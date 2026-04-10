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

      # Create wrapper script that generates config and starts vikunja
      cat > $out/bin/vikunja-wrapper << 'WRAPPER'
#!/bin/sh
PORT="''${PORT:-8080}"

mkdir -p files

if [ ! -f config.yml ]; then
  cat > config.yml << EOF
service:
  interface: ":''${PORT}"
  frontendurl: "''${VIKUNJA_FRONTEND_URL:-http://localhost:''${PORT}/}"

database:
  type: postgres
  host: ''${PGHOST:-localhost}
  port: ''${PGPORT:-5432}
  database: ''${PGDATABASE:-vikunja}
  user: ''${PGUSER:-vikunja}
  password: ''${PGPASSWORD:-}

files:
  basepath: ./files
EOF
fi

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
