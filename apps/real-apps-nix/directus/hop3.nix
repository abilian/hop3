# hop3.nix - Nix expression for Directus deployment
#
# Directus ships on npm only (no prebuilt release tarball) and its
# published JS build assumes the pnpm content-addressed node_modules
# layout — named ESM imports target paths like
# `node_modules/.pnpm/<pkg>@<ver>/...` which npm's flat install doesn't
# create, so the previous npm-based build crashed with
# "Named export 'Type' not found ... is a CommonJS module" at runtime.
# We now install via pnpm inside the Nix build with `__noChroot = true`
# (network access needed to fetch the npm registry). The resulting
# virtual-store symlinks under node_modules/.pnpm are relative to
# $out/app and survive unchanged at deploy time — the hedgedoc-style
# "symlinks break on cp -r" class of failure doesn't apply here
# because we never cp the tree, just symlink node_modules/ into the
# app's writable cwd at startup.

{ pkgs ? import <nixpkgs> {} }:

let
  nodejs = pkgs.nodejs_22;
  pnpm = pkgs.pnpm_9;
  version = "11.17.2";

  app = pkgs.stdenv.mkDerivation {
    pname = "directus";
    inherit version;
    __noChroot = true;
    meta.description = "Open-source headless CMS";

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ nodejs pnpm ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3
      cd $out/app

      export HOME=$TMPDIR
      export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
      # pnpm (like npm) needs NODE_EXTRA_CA_CERTS for registry SSL
      # verification inside the Nix sandbox.
      export NODE_EXTRA_CA_CERTS=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt

      # Seed a package.json so pnpm has a project to install into.
      cat > package.json <<JSON
      {
        "name": "hop3-directus",
        "version": "${version}",
        "private": true,
        "dependencies": {
          "directus": "${version}",
          "pg": "^8.11.0"
        }
      }
      JSON

      # --package-import-method=copy forces copies instead of hardlinks
      # from ~/.local/share/pnpm. Hardlinks inherit pnpm's content-
      # addressed "readonly" mode, which then trips EPERM when pnpm
      # tries to chmod +x the bin shims inside $out/app/node_modules.
      ${pnpm}/bin/pnpm install \
        --config.confirmModulesPurge=false \
        --config.package-import-method=copy \
        --prod \
        --reporter=silent

      cat > $out/bin/directus-start << 'WRAPPER'
      #!/bin/sh
      set -e

      # pnpm's node_modules/.bin/directus picks node from PATH. The
      # hop3-dev server ships Node 18.19.1 which rejects named ESM
      # imports of CommonJS modules (e.g. @sinclair/typebox) with
      # "Named export 'Type' not found". Directus 11.x needs Node 22,
      # so we prepend the Nix-built Node 22 to PATH.
      export PATH="NODEBIN:''${PATH}"

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

      # Symlink the pnpm-installed tree into the writable cwd. The
      # virtual-store symlinks inside node_modules/.pnpm are relative
      # to node_modules/, so symlinking node_modules/ itself preserves
      # the whole graph without copying.
      ln -sfn APPDIR/node_modules ./node_modules
      ln -sfn APPDIR/package.json ./package.json

      APPDIR/node_modules/.bin/directus bootstrap
      exec APPDIR/node_modules/.bin/directus start
      WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/directus-start
      sed -i "s|NODEBIN|${nodejs}/bin|g" $out/bin/directus-start
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
