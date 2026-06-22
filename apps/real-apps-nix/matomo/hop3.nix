# hop3.nix - Nix expression for Matomo deployment
#
# Downloads Matomo analytics platform and serves with PHP built-in server.
# Requires MySQL addon.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "5.0.1";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.mysqli
    all.pdo_mysql
    all.gd
    all.mbstring
    all.xml
    all.curl
    all.zip
    all.zlib
    all.intl
  ]);

  matomoSrc = pkgs.fetchurl {
    url = "https://builds.matomo.org/matomo-${version}.tar.gz";
    sha256 = "4dtIUinaEPtuEaangdlaIsw0xduG4AeUEaIUJ0IJ8Dw=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "matomo";
    inherit version;
    meta = {
      description = "Open source web analytics platform";
    };

    src = matomoSrc;

    dontBuild = true;

    unpackPhase = ''
      tar xzf $src --strip-components=1
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/
      mkdir -p $out/app/tmp/assets $out/app/tmp/cache $out/app/tmp/logs $out/app/tmp/tcpdf $out/app/tmp/templates_c

      cat > $out/bin/matomo << 'WRAPPER'
#!/bin/sh

# Copy app from read-only Nix store to writable cwd
cp -a $out/app/. .
chmod -R u+w .
mkdir -p tmp

# Generate config if not present
if [ ! -f config/config.ini.php ]; then
  mkdir -p config
  cat > config/config.ini.php << CFGEOF
; <?php exit; ?> DO NOT REMOVE THIS LINE
[database]
host = "''${MYSQL_HOST:-127.0.0.1}"
username = "''${MYSQL_USER:-matomo}"
password = "''${MYSQL_PASSWORD:-}"
dbname = "''${MYSQL_DATABASE:-matomo}"
port = ''${MYSQL_PORT:-3306}
tables_prefix = "matomo_"

[General]
trusted_hosts[] = "localhost:''${PORT:-8080}"
CFGEOF
fi

exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t .
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/matomo
      chmod +x $out/bin/matomo

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/matomo"
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
