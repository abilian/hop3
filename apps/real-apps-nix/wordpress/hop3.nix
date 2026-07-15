# hop3.nix - Nix expression for WordPress deployment
#
# Downloads WordPress and serves it with PHP built-in server.
# Requires MySQL addon.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "6.4.2";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.mysqli
    all.pdo_mysql
    all.gd
    all.zip
    all.curl
    all.mbstring
    all.xml
    all.intl
    all.exif
  ]);

  wordpressSrc = pkgs.fetchurl {
    url = "https://wordpress.org/wordpress-${version}.tar.gz";
    sha256 = "m4KJELf5zs3gwAQPmAhoPe2rhopZFsYN6OzAv6Wzo6c=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "wordpress";
    inherit version;
    meta = {
      description = "Popular open source content management system";
    };

    src = wordpressSrc;

    dontBuild = true;

    unpackPhase = ''
      tar xzf $src --strip-components=1
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/
      mkdir -p $out/app/wp-content/uploads $out/app/wp-content/plugins $out/app/wp-content/themes

      # The old setup script was inert and is gone. It guarded on $MYSQL_URL — a
      # variable Hop3 never injects (the mysql addon provides DATABASE_URL and
      # MYSQL_HOST/PORT/DATABASE/USER/PASSWORD) — so its body never ran; it wrote
      # into $out/app (the read-only store) so it could not have run anyway; it
      # copied wp-config-sample.php verbatim, placeholders and all; and it hid all
      # of that behind `2>/dev/null || true`. Net effect: no wp-config.php, so
      # WordPress 302'd /wp-admin/install.php to "Setup Configuration File".
      cat > $out/bin/wordpress << 'WRAPPER'
#!/bin/sh
set -e

# The Nix store is read-only, and WordPress needs a writable docroot
# (wp-config.php, wp-content/uploads). Serve from a cwd copy.
cp -a $out/app/. .
chmod -R u+w .
mkdir -p wp-content/uploads wp-content/plugins wp-content/themes

# Render wp-config.php from the mysql addon env. The 'PHPEOF' marker is QUOTED,
# so the shell expands nothing here: PHP reads each value itself via getenv() at
# request time, and the DB password is never written to disk.
cat > wp-config.php << 'PHPEOF'
<?php
define( 'DB_NAME', getenv('MYSQL_DATABASE') );
define( 'DB_USER', getenv('MYSQL_USER') );
define( 'DB_PASSWORD', getenv('MYSQL_PASSWORD') );
define( 'DB_HOST', getenv('MYSQL_HOST') . ':' . getenv('MYSQL_PORT') );
define( 'DB_CHARSET', 'utf8mb4' );
define( 'DB_COLLATE', ''' );
define( 'WP_DEBUG', getenv('WP_DEBUG') === 'true' );
$table_prefix = 'wp_';
if ( ! defined( 'ABSPATH' ) ) {
    define( 'ABSPATH', __DIR__ . '/' );
}
require_once ABSPATH . 'wp-settings.php';
PHPEOF

exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t .
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/wordpress
      chmod +x $out/bin/wordpress

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/wordpress"
  },
  "env": {
    "WP_DEBUG": "false"
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
    WP_DEBUG = "false";
  };
}
