# hop3.nix - Nix expression for Clojure deployment
#
# This file defines how to build and run this Clojure application.
# Hop3's NixBuilder will evaluate this to produce a BuildArtifact.
#
# Note: Uses pre-built uberjar to avoid Maven dependency downloads during
# Nix build. The JAR was built with: lein uberjar

{ pkgs ? import <nixpkgs> {} }:

let
  # Use headless JDK to avoid GUI dependencies
  jdk = pkgs.jdk17_headless;

  app = pkgs.stdenv.mkDerivation {
    pname = "clojure-hello";
    version = "0.1.0";
    meta = {
      description = "Simple Clojure hello world for Hop3 Nix integration";
    };

    src = ./.;

    nativeBuildInputs = [ jdk ];

    # No build needed - use pre-built JAR
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/lib $out/bin

      # Copy pre-built uberjar
      cp lib/clojure-hello-0.1.0-standalone.jar $out/lib/

      # Create wrapper script
      cat > $out/bin/clojure-hello << EOF
#!/bin/sh
exec ${jdk}/bin/java -jar $out/lib/clojure-hello-0.1.0-standalone.jar "\$@"
EOF
      chmod +x $out/bin/clojure-hello

      # Write runtime metadata for Hop3
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
