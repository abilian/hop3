# hop3.nix - Nix expression for Matomo deployment
#
# Downloads Matomo analytics platform and serves with PHP built-in server.
# Requires MySQL addon.

{ pkgs ? import <nixpkgs> {} }:

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
exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t $out/app
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
