# hop3.nix - Nix expression for Clojure deployment
#
# This file defines how to build and run this Clojure application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.

{ pkgs ? import <nixpkgs> {} }:

let
  jdk = pkgs.jdk17;
  leiningen = pkgs.leiningen;

  app = pkgs.stdenv.mkDerivation {
    pname = "clojure-hello";
    version = "0.1.0";
    meta = {
      description = "Simple Clojure hello world for Hop3 Nix integration";
    };

    src = ./.;

    buildInputs = [ jdk leiningen ];

    buildPhase = ''
      export HOME=$TMPDIR
      export LEIN_HOME=$TMPDIR/.lein
      mkdir -p $LEIN_HOME
      ${leiningen}/bin/lein uberjar
    '';

    installPhase = ''
      mkdir -p $out/lib $out/bin

      cp target/uberjar/clojure-hello-0.1.0-standalone.jar $out/lib/

      cat > $out/bin/clojure-hello << EOF
#!/bin/sh
exec ${jdk}/bin/java -jar $out/lib/clojure-hello-0.1.0-standalone.jar "\$@"
EOF
      chmod +x $out/bin/clojure-hello

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/clojure-hello"
  },
  "env": {},
  "path": [
    "$out/bin",
    "${jdk}/bin"
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
