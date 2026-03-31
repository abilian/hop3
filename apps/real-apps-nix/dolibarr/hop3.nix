# hop3.nix - Nix expression for Dolibarr deployment
#
# Downloads Dolibarr ERP/CRM and serves with PHP built-in server.
# Requires PostgreSQL addon.

{ pkgs ? import <nixpkgs> {} }:

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
exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t $out/app/htdocs
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
    DOLI_ADMIN_LOGIN = "admin";
  };
}
