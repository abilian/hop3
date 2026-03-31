# hop3.nix - Nix expression for BookStack deployment
#
# Downloads BookStack and builds with composer.
# Laravel-based wiki platform requiring MySQL.

{ pkgs ? import <nixpkgs> {} }:

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
exec ${php}/bin/php $out/app/artisan serve --host=0.0.0.0 --port=''${PORT:-8080}
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
