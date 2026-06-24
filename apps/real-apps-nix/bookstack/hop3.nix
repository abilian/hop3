# hop3.nix - Nix expression for BookStack deployment
#
# Downloads BookStack and builds with composer.
# Laravel-based wiki platform requiring MySQL.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "24.02";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.mysqli
    all.pdo_mysql
    all.gd
    all.mbstring
    all.xml
    all.curl
    all.zip
    all.tokenizer
    all.bcmath
    all.intl
    all.ldap
  ]);

  composer = pkgs.php82Packages.composer;

  bookstackSrc = pkgs.fetchurl {
    url = "https://github.com/BookStackApp/BookStack/archive/refs/tags/v${version}.tar.gz";
    sha256 = "CDJ0X2x274ohrevyH+9w4J/wY9SEpdJTNO2MA0resLI=";
  };

  app = pkgs.stdenv.mkDerivation {
    # Allow network access during build (npm/composer/pip install)
    __noChroot = true;
    pname = "bookstack";
    inherit version;
    meta = {
      description = "Simple, self-hosted documentation platform";
    };

    src = bookstackSrc;

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
      mkdir -p $out/app/storage/app $out/app/storage/framework/{cache,sessions,views} $out/app/storage/logs $out/app/bootstrap/cache

      cat > $out/bin/bookstack << 'WRAPPER'
#!/bin/sh

# Generate .env for Laravel
cat > .env << ENVEOF
APP_ENV=''${APP_ENV:-production}
APP_DEBUG=''${APP_DEBUG:-false}
APP_KEY=''${APP_KEY}
APP_URL=http://localhost:''${PORT:-8080}
DB_CONNECTION=mysql
DB_HOST=''${DB_HOST:-127.0.0.1}
DB_PORT=''${DB_PORT:-3306}
DB_DATABASE=''${DB_DATABASE:-bookstack}
DB_USERNAME=''${DB_USERNAME:-bookstack}
DB_PASSWORD=''${DB_PASSWORD:-}
ENVEOF

# Copy app from read-only Nix store to writable cwd
cp -a $out/app/. .
chmod -R u+w .
mkdir -p storage/app storage/framework/cache storage/framework/sessions storage/framework/views storage/logs bootstrap/cache

# Run database migration
${php}/bin/php artisan migrate --force 2>/dev/null || true

exec ${php}/bin/php ./artisan serve --host=0.0.0.0 --port=''${PORT:-8080}
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/bookstack
      chmod +x $out/bin/bookstack

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/bookstack"
  },
  "env": {
    "APP_ENV": "production",
    "APP_DEBUG": "false"
  },
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
  env = {
    APP_ENV = "production";
    APP_DEBUG = "false";
  };
}
