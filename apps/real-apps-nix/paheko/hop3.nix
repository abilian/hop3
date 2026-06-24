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

  src = pkgs.fetchurl {
    url = "https://codeload.github.com/paheko/paheko/tar.gz/refs/tags/${version}";
    # Explicit `name` — the URL has no `.tar.gz` suffix (codeload
    # ends at the tag name), so stdenv's unpackPhase can't auto-detect
    # the archive format. Naming it with the extension makes unpacking work.
    name = "paheko-${version}.tar.gz";
    sha256 = "sha256-D83byx+kmeDvKwiGIMN0lIx25Jp+vR0Mfmk1jCx+Nzw=";
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
        cp -r APPDIR/src paheko-app
        chmod -R u+w paheko-app
      fi

      if [ ! -f paheko-app/config.local.php ]; then
        cat > paheko-app/config.local.php <<CFGEOF
      <?php
      const DATA_ROOT = '$PWD/data';
      const DB_FILE = DATA_ROOT . '/paheko.sqlite';
      const SECRET_KEY = '$(head -c 32 /dev/urandom | base64)';
      CFGEOF
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
