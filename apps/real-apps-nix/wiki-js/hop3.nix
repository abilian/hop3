# hop3.nix - Nix expression for Wiki.js deployment
#
# Downloads the pre-built Wiki.js release and sets up Node.js runtime.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "2.5.303";
  nodejs = pkgs.nodejs_22;

  src = pkgs.fetchurl {
    url = "https://github.com/Requarks/wiki/releases/download/v${version}/wiki-js.tar.gz";
    sha256 = "Jpv4D+ldGPvJz+8cwNhrmC+Ii5dG0UOTC5JIWPwUzvk=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "wiki-js";
    inherit version;
    meta = {
      description = "Modern and powerful wiki platform";
    };

    inherit src;
    sourceRoot = ".";

    # Wiki.js tarball extracts without a top-level directory
    unpackPhase = ''
      mkdir -p source
      tar xzf $src -C source
      sourceRoot=source
    '';

    dontBuild = true;

    buildInputs = [ nodejs ];

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/

      # Create wrapper that generates config.yml and starts Wiki.js
      cat > $out/bin/wiki-js << 'WRAPPER'
#!/bin/sh
export NODE_ENV=production

PORT="''${PORT:-8080}"
DB_HOST="''${PGHOST:-localhost}"
DB_PORT="''${PGPORT:-5432}"
DB_NAME="''${PGDATABASE:-wikijs}"
DB_USER="''${PGUSER:-wikijs}"
DB_PASS="''${PGPASSWORD:-}"

# Wiki.js reads config.yml from the directory containing server/.
# The Nix store is read-only, so we create a writable working directory
# with symlinks to the Nix store app and a local config.yml.
mkdir -p data

# Symlink server and other app directories from Nix store if not present
for item in server node_modules assets package.json; do
  if [ -e APPDIR/$item ] && [ ! -e $item ]; then
    ln -sf APPDIR/$item $item
  fi
done

# Generate config.yml in the working directory
cat > config.yml << EOF
port: ''${PORT}
bindIP: 0.0.0.0

db:
  type: postgres
  host: ''${DB_HOST}
  port: ''${DB_PORT}
  user: ''${DB_USER}
  pass: ''${DB_PASS}
  db: ''${DB_NAME}
  ssl: false

logLevel: info

offline: false
ha: false

dataPath: ./data
EOF

exec NODEPATH/node server/index.js
WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/wiki-js
      sed -i "s|NODEPATH|${nodejs}/bin|g" $out/bin/wiki-js
      chmod +x $out/bin/wiki-js

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/wiki-js"
  },
  "env": {
    "NODE_ENV": "production"
  },
  "path": [
    "$out/bin",
    "${nodejs}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;

  env = {
    NODE_ENV = "production";
  };
}
