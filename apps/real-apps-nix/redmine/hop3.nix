# hop3.nix - redmine (Rails, source-built via bundlerEnv) — PROTOTYPE
# Hand-crafted first to solve the Rails-on-nix problems (writable-home, runtime
# migrate, dynamic Gemfile); the pattern then folds into the ruby-bundler template.
{ pkgs ? import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz") {} }:
let
  ruby = pkgs.ruby_3_2;
  version = "5.1.10";

  src = pkgs.fetchurl {
    url = "https://www.redmine.org/releases/redmine-${version}.tar.gz";
    sha256 = "0hbgzbg38ky1gcs8czbhdw11naarlz81mvmvyzx44kw0l367s60g";
  };

  # bundlerEnv reads ./Gemfile ./Gemfile.lock ./gemset.nix. redmine's Gemfile is
  # dynamic (reads config/database.yml to pick the db gem) — the committed
  # ./config/database.yml (postgres) makes it select pg, matching the lock.
  gems = pkgs.bundlerEnv {
    name = "redmine-gems";
    inherit ruby;
    gemdir = ./.;
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "redmine";
    inherit version src;
    dontConfigure = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3
      cp -r . $out/app/
      # The runtime generates config/database.yml from PG*; drop any shipped one.
      rm -f $out/app/config/database.yml

      cat > $out/bin/redmine <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
# Rails writes into its own tree (config, tmp, files, log) — the Nix store is
# read-only, so lazy-copy into a writable home on first launch (blocker #12).
HOME_DIR="$PWD/.redmine-home"
if [ ! -f "$HOME_DIR/.hop3-ready" ]; then
  mkdir -p "$HOME_DIR"
  cp -rL APPDIR/. "$HOME_DIR"/
  chmod -R u+w "$HOME_DIR"
  touch "$HOME_DIR/.hop3-ready"
fi
cd "$HOME_DIR"

export RAILS_ENV=production
export RAILS_SERVE_STATIC_FILES=1
# bundlerEnv bakes BUNDLE_GEMFILE/BUNDLE_PATH into its bin wrappers, so
# `GEMSBIN/{rake,rails}` use the vendored production gem set.

cat > config/database.yml <<DBYML
production:
  adapter: postgresql
  database: ''${PGDATABASE:-redmine}
  host: ''${PGHOST}
  port: ''${PGPORT:-5432}
  username: ''${PGUSER}
  password: "''${PGPASSWORD}"
  encoding: utf8
DBYML

# Secret token + schema migration are idempotent; safe on every boot.
[ -f config/initializers/secret_token.rb ] || GEMSBIN/rake generate_secret_token
GEMSBIN/rake db:migrate

exec GEMSBIN/rails server -b 0.0.0.0 -p "''${PORT:-3000}"
WRAPPER
      sed -i "s|APPDIR|$out/app|g; s|GEMSBIN|${gems}/bin|g" $out/bin/redmine
      chmod +x $out/bin/redmine

      cat > $out/hop3/runtime.json <<EOF
{
  "workers": { "web": "$out/bin/redmine" },
  "env": {},
  "path": []
}
EOF
    '';
  };
in
{
  package = app;
  env = {};
}
