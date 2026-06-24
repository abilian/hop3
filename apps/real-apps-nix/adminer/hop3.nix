# hop3.nix - Nix expression for Adminer deployment
#
# Single-file PHP database management tool.
# Downloads adminer.php and serves it with PHP built-in server.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "4.8.1";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.mysqli
    all.pgsql
    all.pdo_mysql
    all.pdo_pgsql
    all.pdo_sqlite
  ]);

  adminerSrc = pkgs.fetchurl {
    url = "https://github.com/vrana/adminer/releases/download/v${version}/adminer-${version}.php";
    sha256 = "L9fm2PmHskOrGDkklVH2KtzhlwTEfT0MjdnlfqW5xrM=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "adminer";
    inherit version;
    meta = {
      description = "Database management in a single PHP file";
    };

    src = adminerSrc;

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp $src $out/app/index.php

      cat > $out/bin/adminer << 'WRAPPER'
#!/bin/sh
exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t $out/app
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/adminer
      chmod +x $out/bin/adminer

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/adminer"
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
