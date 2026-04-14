# hop3.nix - Nix expression for Vaultwarden deployment
#
# Vaultwarden is a Bitwarden-compatible password manager implemented
# in Rust. The nixpkgs derivation ships the server binary only; the
# web-vault static assets are exposed via `passthru.webvault`. We
# point WEB_VAULT_FOLDER at that path so the UI is served.
#
# Storage: SQLite by default under $DATA_FOLDER. Set DATABASE_URL
# (postgres://...) to use an addon instead.

{ pkgs ? import <nixpkgs> {} }:

let
  vaultwarden = pkgs.vaultwarden;
  webvault = vaultwarden.webvault;

  app = pkgs.stdenv.mkDerivation {
    pname = "vaultwarden";
    version = vaultwarden.version;
    meta = {
      description = "Bitwarden-compatible password manager (Rust)";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/vaultwarden-wrapper << 'WRAPPER'
      #!/bin/sh
      set -e

      mkdir -p data

      export ROCKET_ADDRESS="0.0.0.0"
      export ROCKET_PORT="''${PORT:-8080}"
      export DATA_FOLDER="''${DATA_FOLDER:-$PWD/data}"
      export WEB_VAULT_FOLDER="${webvault}/share/vaultwarden/vault"
      export WEB_VAULT_ENABLED="true"

      # Database: if DATABASE_URL is set (e.g. by a postgres addon),
      # use it; otherwise default to SQLite in DATA_FOLDER.
      if [ -z "$DATABASE_URL" ]; then
        export DATABASE_URL="$DATA_FOLDER/db.sqlite3"
      fi

      # Disable signups by default; operators enable via env.
      : "''${SIGNUPS_ALLOWED:=false}"
      export SIGNUPS_ALLOWED

      exec ${vaultwarden}/bin/vaultwarden
      WRAPPER
      chmod +x $out/bin/vaultwarden-wrapper

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": {
          "web": "$out/bin/vaultwarden-wrapper"
        },
        "env": {
          "ROCKET_ADDRESS": "0.0.0.0",
          "WEB_VAULT_ENABLED": "true",
          "SIGNUPS_ALLOWED": "false"
        },
        "path": [
          "$out/bin",
          "${vaultwarden}/bin"
        ]
      }
      EOF
    '';
  };

in
{
  package = app;

  env = {
    ROCKET_ADDRESS = "0.0.0.0";
    WEB_VAULT_ENABLED = "true";
    SIGNUPS_ALLOWED = "false";
  };
}
