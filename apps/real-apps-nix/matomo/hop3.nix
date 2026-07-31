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
trusted_hosts[] = "''${HOST_NAME:-localhost}"
salt = "''${MATOMO_SALT:?matomo: MATOMO_SALT not injected}"
# Hop3's nginx terminates TLS and forwards plain HTTP, so Matomo sees `http`,
# decides the request is insecure and answers 302 — which is what
# `GET /index.php returned 302, expected 200` was. Tell it the proxy is
# trustworthy and that the outside world is already on https.
assume_secure_protocol = 1
proxy_client_headers[] = "HTTP_X_FORWARDED_FOR"
proxy_host_headers[] = "HTTP_X_FORWARDED_HOST"
CFGEOF
fi

# Matomo is not usable until its installer has run: without this it answers
# every request with "please run the installer", including the login page the
# smoke test posts to.
# Matomo 5 ships NO console command for installation or for creating a
# superuser — its Installation plugin is a browser wizard a deploy cannot click
# through, which is why `console core:create-superuser` exits 1 on a fresh
# database. scripts/install.php performs the same steps that wizard performs
# (schema, anonymous user, install marker, superuser, first site), each step
# guarded separately so it is idempotent AND resumable.
if [ ! -f .hop3-installed ]; then
  ${php}/bin/php scripts/install.php && touch .hop3-installed
fi

# The schema the installer writes is not necessarily at the code's version, and
# Matomo answers every request with a 302 to `?module=CoreUpdater` until the
# updater has run. Both working variants follow the install with this line; the
# hand-crafted one did not, which is the whole of its "302, expected 200".
${php}/bin/php console core:update --yes 2>&1 | tail -3

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
