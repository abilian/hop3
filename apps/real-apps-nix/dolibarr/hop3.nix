# hop3.nix - Nix expression for Dolibarr deployment
#
# Downloads Dolibarr ERP/CRM and serves with PHP built-in server.
# Requires PostgreSQL addon.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "19.0.3";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.pgsql
    all.pdo_pgsql
    all.gd
    all.mbstring
    all.xml
    all.curl
    all.zip
    all.intl
    all.calendar
    all.imap
    all.ldap
  ]);

  composer = pkgs.php82Packages.composer;

  dolibarrSrc = pkgs.fetchurl {
    url = "https://github.com/Dolibarr/dolibarr/archive/refs/tags/${version}.tar.gz";
    sha256 = "UvzqWjVPhoj6Moq/+qGWv5BW9UUWTNf+iC0bt95lQWM=";
  };

  app = pkgs.stdenv.mkDerivation {
    # Allow network access during build (npm/composer/pip install)
    __noChroot = true;
    pname = "dolibarr";
    inherit version;
    meta = {
      description = "Open source ERP and CRM for small and medium businesses";
    };

    src = dolibarrSrc;

    nativeBuildInputs = [ php composer ];

    unpackPhase = ''
      tar xzf $src --strip-components=1
    '';

    buildPhase = ''
      export COMPOSER_HOME=$(mktemp -d)
      composer install --no-dev --optimize-autoloader --no-interaction || true
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/
      mkdir -p $out/app/documents

      cat > $out/bin/dolibarr << 'WRAPPER'
#!/bin/sh
set -e

# Dolibarr was served straight out of the read-only store, so it could never be
# installed: it answered every request with "Dolibarr config file content seems
# to be not correctly defined. Please run dolibarr setup by calling page
# /install" — including the login page the smoke test posts to.
cp -a $out/app/. .
chmod -R u+w .

# Dolibarr ships no installer CLI, only a browser wizard. Each wizard step also
# reads its inputs from $argv under the PHP CLI, so the same steps can be driven
# from a script; setup-config.sh does that and then verifies the admin row
# exists, because Dolibarr's steps can print an error and still exit 0.
bash scripts/setup-config.sh

exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t ./htdocs
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/dolibarr
      chmod +x $out/bin/dolibarr

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/dolibarr"
  },
  "env": {
    "DOLI_ADMIN_LOGIN": "admin"
  },
  "path": [
    "$out/bin",
    "${php}/bin",
    "${pkgs.postgresql}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;
  env = {
    DOLI_ADMIN_LOGIN = "admin";
  };
}
