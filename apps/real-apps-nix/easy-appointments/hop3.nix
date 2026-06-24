# hop3.nix - Nix expression for Easy!Appointments deployment
#
# Downloads Easy!Appointments and serves with PHP built-in server.
# Appointment scheduling requiring MySQL.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "1.5.0";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.mysqli
    all.pdo_mysql
    all.gd
    all.mbstring
    all.xml
    all.curl
    all.zip
    all.intl
  ]);

  composer = pkgs.php82Packages.composer;

  easyAppointmentsSrc = pkgs.fetchurl {
    url = "https://github.com/alextselegidis/easyappointments/archive/refs/tags/${version}.tar.gz";
    sha256 = "Skz6uMjvtiXaw34st/FxtTljycI4yAyYiqa6qr0Av3I=";
  };

  app = pkgs.stdenv.mkDerivation {
    # Allow network access during build (npm/composer/pip install)
    __noChroot = true;
    pname = "easy-appointments";
    inherit version;
    meta = {
      description = "Open source appointment scheduling";
    };

    src = easyAppointmentsSrc;

    nativeBuildInputs = [ php composer ];

    unpackPhase = ''
      tar xzf $src --strip-components=1
    '';

    buildPhase = ''
      export COMPOSER_HOME=$(mktemp -d)
      composer install --no-dev --optimize-autoloader --no-interaction || true
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/

      cat > $out/bin/easy-appointments << 'WRAPPER'
#!/bin/sh

# Copy app from read-only Nix store to writable cwd
cp -a $out/app/. .
chmod -R u+w .

exec ${php}/bin/php -S 0.0.0.0:''${PORT:-8080} -t .
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/easy-appointments
      chmod +x $out/bin/easy-appointments

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/easy-appointments"
  },
  "env": {
    "APP_URL": "http://localhost:8080"
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
    APP_URL = "http://localhost:8080";
  };
}
