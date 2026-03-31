# hop3.nix - Nix expression for Radicale deployment
#
# Radicale is available as a top-level nixpkgs package (not in python3Packages).

{ pkgs ? import <nixpkgs> {} }:

let
  radicale = pkgs.radicale;

  app = pkgs.stdenv.mkDerivation {
    pname = "radicale";
    version = radicale.version;
    meta.description = "A simple CalDAV and CardDAV server";

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/radicale-start << 'WRAPPER'
#!/bin/sh
mkdir -p collections
exec RADICALE_BIN --server-hosts "0.0.0.0:''${PORT:-8080}" "$@"
WRAPPER
      sed -i "s|RADICALE_BIN|${radicale}/bin/radicale|g" $out/bin/radicale-start
      chmod +x $out/bin/radicale-start

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/radicale-start"
  },
  "env": {
    "RADICALE_AUTH_TYPE": "none"
  },
  "path": ["$out/bin", "${radicale}/bin"]
}
EOF
    '';
  };

in { package = app; }
