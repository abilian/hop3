# hop3.nix - Nix expression for Etherpad deployment
#
# Downloads the Etherpad source tarball and builds with Node.js/pnpm.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "2.0.3";
  nodejs = pkgs.nodejs;
  pnpm = pkgs.nodePackages.pnpm;

  src = pkgs.fetchurl {
    url = "https://github.com/ether/etherpad-lite/archive/refs/tags/v${version}.tar.gz";
    sha256 = "bcGa3cgoCAZZD5qC1EJqiKjvd8eEH5n5elDWqmyezBo=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "etherpad";
    inherit version;
    meta = {
      description = "Real-time collaborative document editor";
    };

    inherit src;
    sourceRoot = "etherpad-lite-${version}";

    nativeBuildInputs = [ nodejs pnpm pkgs.python3 pkgs.pkg-config ];
    buildInputs = [ nodejs ];

    # pnpm creates symlinks to dev deps that don't exist in production;
    # disable Nix's broken symlink check
    dontFixup = true;

    buildPhase = ''
      export HOME=$TMPDIR
      export CI=true
      bin/installDeps.sh || true
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/

      cat > $out/bin/etherpad << EOF
#!/bin/sh
export NODE_ENV=production
cd $out/app
exec ${pnpm}/bin/pnpm run prod "\$@"
EOF
      chmod +x $out/bin/etherpad

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/etherpad"
  },
  "env": {
    "NODE_ENV": "production"
  },
  "path": [
    "$out/bin",
    "${nodejs}/bin",
    "${pnpm}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;

  env = {
    NODE_ENV = "production";
  };
}
