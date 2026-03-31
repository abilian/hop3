# hop3.nix - Nix expression for Wiki.js deployment
#
# Downloads the pre-built Wiki.js release and sets up Node.js runtime.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "2.5.303";
  nodejs = pkgs.nodejs;

  src = pkgs.fetchurl {
    url = "https://github.com/Requarks/wiki/releases/download/v${version}/wiki-js.tar.gz";
    sha256 = "Jpv4D+ldGPvJz+8cwNhrmC+Ii5dG0UOTC5JIWPwUzvk=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "wiki-js";
    inherit version;
    meta = {
      description = "Modern and powerful wiki platform";
    };

    inherit src;
    sourceRoot = ".";

    # Wiki.js tarball extracts without a top-level directory
    unpackPhase = ''
      mkdir -p source
      tar xzf $src -C source
      sourceRoot=source
    '';

    dontBuild = true;

    buildInputs = [ nodejs ];

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/

      cat > $out/bin/wiki-js << EOF
#!/bin/sh
export NODE_ENV=production
cd $out/app
exec ${nodejs}/bin/node server/index.js "\$@"
EOF
      chmod +x $out/bin/wiki-js

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/wiki-js"
  },
  "env": {
    "NODE_ENV": "production"
  },
  "path": [
    "$out/bin",
    "${nodejs}/bin"
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
