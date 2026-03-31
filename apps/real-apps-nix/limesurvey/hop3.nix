# hop3.nix - Nix expression for LimeSurvey deployment
#
# Downloads LimeSurvey and serves with PHP built-in server.
# Requires PostgreSQL addon.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "6.16.10";
  dateSuffix = "260223";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.pgsql
    all.pdo_pgsql
    all.gd
    all.mbstring
    all.xml
    all.curl
    all.zip
    all.intl
    all.ldap
    all.imap
  ]);

  limesurveyZip = pkgs.fetchurl {
    url = "https://download.limesurvey.org/latest-master/limesurvey${version}+${dateSuffix}.zip";
    sha256 = "jXRc89eWmPd354Zk2peRJR7v4G9ePwTJT9BS2es3tnk=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "limesurvey";
    inherit version;
    meta = {
      description = "Professional online survey and data collection tool";
    };

    src = limesurveyZip;

    nativeBuildInputs = [ pkgs.unzip ];

    dontBuild = true;

    unpackPhase = ''
      unzip -q $src
      mv limesurvey/* . 2>/dev/null || mv limesurvey*/* . 2>/dev/null || true
      rm -rf limesurvey
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/
      mkdir -p $out/app/tmp $out/app/upload

      cat > $out/bin/limesurvey << 'WRAPPER'
#!/bin/sh
exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t $out/app
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/limesurvey
      chmod +x $out/bin/limesurvey

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/limesurvey"
  },
  "env": {
    "ADMIN_USER": "admin",
    "ADMIN_NAME": "Administrator",
    "ADMIN_EMAIL": "admin@example.com"
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
    ADMIN_USER = "admin";
    ADMIN_NAME = "Administrator";
    ADMIN_EMAIL = "admin@example.com";
  };
}
