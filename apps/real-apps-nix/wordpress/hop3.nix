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

      # Create setup script that generates wp-config.php at runtime
      cat > $out/bin/wordpress-setup << 'SETUP'
#!/bin/sh
APP_DIR="$out/app"
if [ -n "$MYSQL_URL" ] && [ ! -f "$APP_DIR/wp-config.php" ]; then
  cp "$APP_DIR/wp-config-sample.php" "$APP_DIR/wp-config.php" 2>/dev/null || true
fi
SETUP
      sed -i "s|\$out|$out|g" $out/bin/wordpress-setup
      chmod +x $out/bin/wordpress-setup

      cat > $out/bin/wordpress << 'WRAPPER'
#!/bin/sh
$out/bin/wordpress-setup
exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t $out/app
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
