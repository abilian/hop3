# hop3.nix - Nix expression for Vikunja deployment
#
# Downloads the pre-built Vikunja binary and creates a wrapper
# that generates configuration and starts the server.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "0.24.6";

  vikunja-release = pkgs.fetchurl {
    url = "https://dl.vikunja.io/vikunja/${version}/vikunja-v${version}-linux-amd64-full.zip";
    sha256 = "AAfg+56IAhs5DYmK2IpE2JgdUv7lfsGeBYZwOvso8Bo=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "vikunja";
    inherit version;
    meta = {
      description = "Open source task and project management";
    };

    src = vikunja-release;
    sourceRoot = ".";

    nativeBuildInputs = [ pkgs.unzip ];

    unpackPhase = ''
      unzip $src
    '';

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      # Install the binary (handle multiple naming formats)
      if [ -f "vikunja-v${version}-linux-amd64" ]; then
        cp "vikunja-v${version}-linux-amd64" $out/bin/vikunja
      elif [ -f "vikunja-${version}-linux-amd64" ]; then
        cp "vikunja-${version}-linux-amd64" $out/bin/vikunja
      elif [ -f "vikunja" ]; then
        cp vikunja $out/bin/vikunja
      fi
      chmod +x $out/bin/vikunja

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

exec BINDIR/vikunja
WRAPPER
      sed -i "s|BINDIR|$out/bin|g" $out/bin/vikunja-wrapper
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
    VIKUNJA_FRONTEND_URL = "http://localhost:8080/";
  };
}
