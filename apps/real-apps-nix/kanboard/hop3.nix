# hop3.nix - Nix expression for Kanboard deployment
#
# Downloads Kanboard and serves with PHP built-in server.
# Kanban project management requiring MySQL.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "1.2.37";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.mysqli
    all.pdo_mysql
    all.pdo_sqlite
    all.gd
    all.mbstring
    all.xml
    all.curl
    all.zip
    all.ldap
  ]);

  kanboardSrc = pkgs.fetchurl {
    url = "https://github.com/kanboard/kanboard/archive/refs/tags/v${version}.tar.gz";
    sha256 = "TVOLDXS3rX4n4cMQiztpkwmkYAbkTDhagD2+wZ+Erv8=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "kanboard";
    inherit version;
    meta = {
      description = "Kanban project management software";
    };

    src = kanboardSrc;

    dontBuild = true;

    unpackPhase = ''
      tar xzf $src --strip-components=1
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/
      mkdir -p $out/app/data $out/app/plugins

      cat > $out/bin/kanboard << 'WRAPPER'
#!/bin/sh
exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t $out/app
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/kanboard
      chmod +x $out/bin/kanboard

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/kanboard"
  },
  "env": {
    "DEBUG": "false"
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
    DEBUG = "false";
  };
}
