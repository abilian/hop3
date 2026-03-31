# hop3.nix - Nix expression for Nextcloud deployment
#
# Downloads Nextcloud and serves with PHP built-in server.
# Self-hosted productivity platform requiring MySQL.

{ pkgs ? import <nixpkgs> {} }:

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
exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t $out/app
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
