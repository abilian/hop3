# hop3.nix - Nix expression for Miniflux deployment
#
# Wraps the nixpkgs miniflux package (built from source by nixpkgs)
# with a startup wrapper that configures it for Hop3.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

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
# No defaults. `ADMIN_PASSWORD="''${ADMIN_PASSWORD:-changeme}"` meant every
# deployment had an administrator whose password is published in this
# repository, while the operator was handed a generated one that did not work —
# and the smoke test only ever saw the second half of that.
export ADMIN_USERNAME="''${ADMIN_USERNAME:?miniflux: ADMIN_USERNAME not injected}"
export ADMIN_PASSWORD="''${ADMIN_PASSWORD:?miniflux: ADMIN_PASSWORD not injected — refusing to create an admin with a default password}"

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
    "CREATE_ADMIN": "1"
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

  # The admin credential is injected by Hop3 (see [env.computed] in hop3.toml),
  # never defaulted here.
  env = {
    RUN_MIGRATIONS = "1";
    CREATE_ADMIN = "1";
  };
}
