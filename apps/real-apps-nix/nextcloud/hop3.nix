# hop3.nix - Nix expression for Nextcloud deployment
#
# Downloads Nextcloud and serves with PHP built-in server.
# Self-hosted productivity platform requiring MySQL.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "28.0.2";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.mysqli
    all.pdo_mysql
    all.gd
    all.mbstring
    all.xml
    all.curl
    all.zip
    all.intl
    all.bcmath
    all.gmp
    all.exif
    all.apcu
    all.opcache
    all.fileinfo
  ]);

  nextcloudSrc = pkgs.fetchurl {
    url = "https://download.nextcloud.com/server/releases/nextcloud-${version}.tar.bz2";
    sha256 = "3jTWuvPszqz90TjoVSDNheHSzmeY2f+keKwX6x76HQg=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "nextcloud";
    inherit version;
    meta = {
      description = "Self-hosted productivity platform";
    };

    src = nextcloudSrc;

    dontBuild = true;

    unpackPhase = ''
      tar xjf $src --strip-components=1
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/
      mkdir -p $out/app/data $out/app/config

      cat > $out/bin/nextcloud << 'WRAPPER'
#!/bin/sh

# Copy app from read-only Nix store to writable cwd
cp -a $out/app/. .
chmod -R u+w .
mkdir -p data config

# Generate autoconfig if not present
if [ ! -f config/autoconfig.php ]; then
  cat > config/autoconfig.php << 'CFGEOF'
<?php
$AUTOCONFIG = array(
  "dbtype" => "mysql",
  "dbname" => getenv("MYSQL_DATABASE") ?: "nextcloud",
  "dbuser" => getenv("MYSQL_USER") ?: "nextcloud",
  "dbpass" => getenv("MYSQL_PASSWORD") ?: "",
  "dbhost" => getenv("MYSQL_HOST") ?: "127.0.0.1",
  // MUST be absolute. A relative datadirectory makes OC_Util::checkServer()
  // ("Your data directory must be an absolute path") 503 EVERY request, forever
  // — and install has already written installed=>true by then, so the instance
  // is wedged and a redeploy won't heal it. autoconfig.php lives in <cwd>/config,
  // so dirname(__DIR__) is the app's src dir; __DIR__ is absolute regardless of cwd.
  "directory" => dirname(__DIR__) . "/data",
  "adminlogin" => getenv("NEXTCLOUD_ADMIN_USER") ?: "admin",
  "adminpass" => getenv("NEXTCLOUD_ADMIN_PASSWORD") ?: "admin123",
);
CFGEOF
fi

exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t .
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/nextcloud
      chmod +x $out/bin/nextcloud

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/nextcloud"
  },
  "env": {
    "NEXTCLOUD_ADMIN_USER": "admin"
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
    NEXTCLOUD_ADMIN_USER = "admin";
  };
}
