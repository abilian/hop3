# hop3.nix - Nix expression for Paheko deployment
#
# Paheko is a PHP application with a SQLite database. It's not in
# nixpkgs, so we fetch the release tarball and run it with the PHP
# built-in server. No composer step: Paheko vendors everything.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "1.3.15";
  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.sqlite3 all.gd all.mbstring all.xml all.zip all.curl all.intl
  ]);

  # The upstream RELEASE, not the git tag. Paheko vendors the KD2 framework into
  # its release archive and does not commit it, so a package built from
  # codeload's tag is missing part of the application: every start died on
  # `require_once .../include/lib/KD2/ErrorManager.php`. The release also has a
  # FLAT layout (`include/`, `www/`, `modules/` at the root) where the tag put
  # everything under `src/` — see the copy in the wrapper below.
  src = pkgs.fetchurl {
    url = "https://fossil.kd2.org/paheko/uv/paheko-${version}.tar.gz";
    sha256 = "sha256-p7PbPJi22BkZO3NVq/cX9SOVvTupvPbGh96e8AjKT98=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "paheko";
    inherit version;
    meta.description = "Nonprofit accounting and association management";

    inherit src;
    sourceRoot = "paheko-${version}";

    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3
      cp -r . $out/app

      cat > $out/bin/paheko-start << 'WRAPPER'
      #!/bin/sh
      set -e

      mkdir -p data
      # Use `paheko-app` as the local copy directory rather than `src`
      # — Hop3's chdir lands us inside a directory already named `src`,
      # so `./src` is too confusing. Paheko writes config.local.php
      # into its own root, so the local copy must be writable.
      if [ ! -d paheko-app ]; then
        cp -r APPDIR/. paheko-app
        chmod -R u+w paheko-app
      fi

      # config.local.php MUST declare `namespace Paheko;`. Without it these are
      # GLOBAL constants that Paheko never reads — it looks up Paheko\DB_FILE —
      # so it silently falls back to its defaults and every setting here is
      # ignored. Guarded `defined() || define()` rather than bare `const`: the
      # file is required with a plain `require`, and a second bootstrap in one
      # process turns the redefinition warning into a fatal.
      #
      # SECRET_KEY comes from the platform's generated-once value. It used to be
      # minted inline with `$(head -c 32 /dev/urandom | base64)`, which is stable
      # only for as long as this file survives — and it does not survive a
      # redeploy that replaces the tree.
      if [ ! -f paheko-app/config.local.php ]; then
        cat > paheko-app/config.local.php <<CFGEOF
      <?php
      namespace Paheko;
      defined('Paheko\DATA_ROOT') || define('Paheko\DATA_ROOT', '$PWD/data');
      defined('Paheko\DB_FILE') || define('Paheko\DB_FILE', DATA_ROOT . '/paheko.sqlite');
      defined('Paheko\SECRET_KEY') || define('Paheko\SECRET_KEY', "''${PAHEKO_SECRET_KEY:?paheko: PAHEKO_SECRET_KEY not injected}");
      # Left unset, Paheko auto-detects its address from \$_SERVER — and behind
      # Hop3 it is reached over plain HTTP by the proxy that terminates TLS, so
      # it concluded it lived at http:// and rendered exactly that.
      defined('Paheko\WWW_URL') || define('Paheko\WWW_URL', "''${HOP3_PUBLIC_URL:?paheko: HOP3_PUBLIC_URL not injected}/");
      CFGEOF
      fi

      # Headless install: schema + first admin in one pass, no browser wizard.
      # Without it `/admin/login.php` answers 302 to the installer. The password
      # goes through a mode-600 file so it never appears in argv or `ps`.
      if [ ! -s data/paheko.sqlite ]; then
        PW_FILE="$(mktemp)"
        chmod 600 "$PW_FILE"
        trap 'rm -f "$PW_FILE"' EXIT
        printf '%s' "''${HOP3_ADMIN_PASSWORD:?paheko: HOP3_ADMIN_PASSWORD not injected}" > "$PW_FILE"
        (cd paheko-app && ${php}/bin/php bin/paheko init \
          --country "''${PAHEKO_COUNTRY:-FR}" \
          --orgname "''${PAHEKO_ORG_NAME:-Paheko}" \
          --name "''${HOP3_ADMIN_USER:?paheko: HOP3_ADMIN_USER not injected}" \
          --email "''${HOP3_ADMIN_EMAIL:?paheko: HOP3_ADMIN_EMAIL not injected}" \
          --password-file "$PW_FILE")
        rm -f "$PW_FILE"
        trap - EXIT
      fi

      exec ${php}/bin/php -S "0.0.0.0:''${PORT:-8080}" -t paheko-app/www
      WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/paheko-start
      chmod +x $out/bin/paheko-start

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": {
          "web": "$out/bin/paheko-start"
        },
        "env": {},
        "path": [
          "$out/bin",
          "${php}/bin"
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
