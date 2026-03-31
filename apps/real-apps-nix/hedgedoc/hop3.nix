# hop3.nix - Nix expression for HedgeDoc deployment
#
# Uses the pre-built HedgeDoc release tarball (includes node_modules).
# Building from source with npm takes 10+ minutes — use the release instead.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "1.9.9";
  nodejs = pkgs.nodejs_20;

  src = pkgs.fetchurl {
    url = "https://github.com/hedgedoc/hedgedoc/releases/download/${version}/hedgedoc-${version}.tar.gz";
    sha256 = "F2nTDmBFgEBHWm109TlSEBlixAw5B2Xhnm/28/5wwAg=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "hedgedoc";
    inherit version;
    meta.description = "Real-time collaborative markdown editor";

    inherit src;
    sourceRoot = ".";

    # Pre-built release — no build needed
    dontBuild = true;
    # Release tarball may have broken dev-dep symlinks
    dontFixup = true;

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3

      cp -r . $out/app/

      cat > $out/bin/hedgedoc << EOF
#!/bin/sh
export NODE_ENV=production
cd $out/app
exec ${nodejs}/bin/node app.js "\$@"
EOF
      chmod +x $out/bin/hedgedoc

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/hedgedoc"
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
  env = { NODE_ENV = "production"; };
}
