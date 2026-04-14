# hop3.nix - Nix expression for Directus deployment
#
# Directus ships on npm only (no prebuilt release tarball). Install
# via npm inside the Nix build with `__noChroot = true` so the sandbox
# permits network access. The resulting node_modules tree lives under
# $out/app/node_modules.

{ pkgs ? import <nixpkgs> {} }:

let
  nodejs = pkgs.nodejs_22;
  version = "11.17.2";

  app = pkgs.stdenv.mkDerivation {
    pname = "directus";
    inherit version;
    __noChroot = true;
    meta.description = "Open-source headless CMS";

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ nodejs ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3
      cd $out/app

      export HOME=$TMPDIR
      export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
      # npm reads its own CA bundle via NODE_EXTRA_CA_CERTS, not
      # SSL_CERT_FILE; without it, npm fails with
      # UNABLE_TO_GET_ISSUER_CERT_LOCALLY inside the Nix sandbox.
      export NODE_EXTRA_CA_CERTS=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt

      ${nodejs}/bin/npm init -y
      ${nodejs}/bin/npm install --no-audit --no-fund --loglevel=error \
        "directus@${version}" \
        "pg@^8.11.0"

      cat > $out/bin/directus-start << 'WRAPPER'
      #!/bin/sh
      set -e

      export DB_CLIENT="''${DB_CLIENT:-pg}"
      export DB_HOST="''${PGHOST}"
      export DB_PORT="''${PGPORT:-5432}"
      export DB_DATABASE="''${PGDATABASE}"
      export DB_USER="''${PGUSER}"
      export DB_PASSWORD="''${PGPASSWORD}"

      export HOST="0.0.0.0"
      export PORT="''${PORT:-8055}"
      export PUBLIC_URL="''${PUBLIC_URL:-http://localhost:''${PORT}}"
      export KEY="''${KEY:-$(head -c 32 /dev/urandom | base64)}"
      export SECRET="''${SECRET:-$(head -c 32 /dev/urandom | base64)}"
      export ADMIN_EMAIL="''${ADMIN_EMAIL:-admin@example.com}"
      export ADMIN_PASSWORD="''${ADMIN_PASSWORD:-$(head -c 16 /dev/urandom | base64)}"

      # Symlink node_modules into the writable cwd so the directus binary
      # can resolve it from where it expects.
      ln -sfn APPDIR/node_modules ./node_modules
      ln -sfn APPDIR/package.json ./package.json

      APPDIR/node_modules/.bin/directus bootstrap
      exec APPDIR/node_modules/.bin/directus start
      WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/directus-start
      chmod +x $out/bin/directus-start

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": {
          "web": "$out/bin/directus-start"
        },
        "env": {},
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
  env = {};
}
