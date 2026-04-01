# hop3.nix - Nix expression for Clojure deployment
#
# Builds the uberjar with Leiningen on the server.
# Leiningen downloads Maven dependencies during build (__noChroot needed).

{ pkgs ? import <nixpkgs> {} }:

let
  jdk = pkgs.jdk17_headless;
  leiningen = pkgs.leiningen;

  app = pkgs.stdenv.mkDerivation {
    pname = "clojure-hello";
    version = "0.1.0";
    __noChroot = true;  # lein uberjar downloads Maven deps
    meta.description = "Simple Clojure hello world for Hop3 Nix integration";

    src = ./.;

    nativeBuildInputs = [ jdk leiningen ];

    buildPhase = ''
      export HOME=$TMPDIR
      export LEIN_HOME=$TMPDIR/.lein
      export M2_HOME=$TMPDIR/.m2
      export _JAVA_OPTIONS="-Duser.home=$TMPDIR"
      lein uberjar
    '';

    installPhase = ''
      mkdir -p $out/lib $out/bin $out/hop3

      cp target/uberjar/clojure-hello-0.1.0-standalone.jar $out/lib/

      cat > $out/bin/clojure-hello << EOF
#!/bin/sh
exec ${jdk}/bin/java -jar $out/lib/clojure-hello-0.1.0-standalone.jar "\$@"
EOF
      chmod +x $out/bin/clojure-hello

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
