# hop3.nix - Nix expression for Invoice Ninja deployment
#
# Downloads Invoice Ninja and builds with composer.
# Laravel-based invoicing platform requiring MySQL.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "5.8.37";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.mysqli
    all.pdo_mysql
    all.gd
    all.mbstring
    all.xml
    all.curl
    all.zip
    all.bcmath
    all.intl
    all.soap
    all.fileinfo
    all.tokenizer
  ]);

  composer = pkgs.php82Packages.composer;

  invoiceNinjaSrc = pkgs.fetchurl {
    url = "https://github.com/invoiceninja/invoiceninja/archive/refs/tags/v${version}.tar.gz";
    sha256 = "7NZs3hAxH3awKMeIlwqem6gnVCRGdpDvZZ+7SW033qY=";
  };

  app = pkgs.stdenv.mkDerivation {
    # Allow network access during build (npm/composer/pip install)
    __noChroot = true;
    pname = "invoice-ninja";
    inherit version;
    meta = {
      description = "Free open-source invoicing platform";
    };

    src = invoiceNinjaSrc;

    nativeBuildInputs = [ php composer pkgs.nodejs ];

    unpackPhase = ''
      tar xzf $src --strip-components=1
    '';

    buildPhase = ''
      export COMPOSER_HOME=$(mktemp -d)
      composer install --no-dev --optimize-autoloader --no-interaction --ignore-platform-reqs || true
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/
      mkdir -p $out/app/storage/app $out/app/storage/framework/{cache,sessions,views} $out/app/storage/logs $out/app/bootstrap/cache $out/app/public/storage

      cat > $out/bin/invoice-ninja << 'WRAPPER'
#!/bin/sh

# Generate .env for Laravel
cat > .env << ENVEOF
APP_ENV=''${APP_ENV:-production}
APP_DEBUG=''${APP_DEBUG:-false}
APP_KEY=''${APP_KEY}
# Laravel derives the scheme and host of every redirect from APP_URL; pinned to
# localhost, `/` bounces until the browser gives up with ERR_TOO_MANY_REDIRECTS.
APP_URL=''${HOP3_PUBLIC_URL:-http://localhost:''${PORT:-8080}}
REQUIRE_HTTPS=false
DB_CONNECTION=mysql
DB_HOST=''${DB_HOST:-127.0.0.1}
DB_PORT=''${DB_PORT:-3306}
DB_DATABASE=''${DB_DATABASE:-invoiceninja}
DB_USERNAME=''${DB_USERNAME:-invoiceninja}
DB_PASSWORD=''${DB_PASSWORD:-}
ENVEOF

# Copy app from read-only Nix store to writable cwd
cp -a $out/app/. .
chmod -R u+w .
mkdir -p storage/app storage/framework/cache storage/framework/sessions storage/framework/views storage/logs bootstrap/cache public/storage

# Migrate, then seed and create the account ONCE. `2>/dev/null || true` hid a
# failing migration and left an app with no schema reporting success — and
# nothing ever created an account, so `POST /api/v1/login` answered 401.
${php}/bin/php artisan migrate --force

if [ ! -f .hop3-account ]; then
  ${php}/bin/php artisan db:seed --force
  ${php}/bin/php artisan ninja:create-account \
    --email="''${HOP3_ADMIN_EMAIL:?invoice-ninja: HOP3_ADMIN_EMAIL not injected}" \
    --password="''${HOP3_ADMIN_PASSWORD:?invoice-ninja: HOP3_ADMIN_PASSWORD not injected}"
  touch .hop3-account
fi

exec ${php}/bin/php ./artisan serve --host=0.0.0.0 --port=''${PORT:-8080}
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/invoice-ninja
      chmod +x $out/bin/invoice-ninja

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/invoice-ninja"
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
