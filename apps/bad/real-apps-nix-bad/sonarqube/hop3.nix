# hop3.nix - Nix expression for SonarQube deployment
#
# SonarQube's sonar.sh resolves its own install dir via `readlink -f`
# and writes into it (conf/sonar.properties, app/temp/sharedmemory,
# SonarQube.pid, etc.). Symlinking the tree into a writable cwd isn't
# enough — the resolved self-path still lands in the read-only nix
# store. We use the lazy cp-to-writable-home pattern (same shape as
# apps/real-apps-nix/keycloak/hop3.nix, and the template-supported
# writable-home-at-runtime for nixpkgs-wrapper apps). One-shot copy
# at first launch, then exec from the writable copy.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "26.2.0.119303";
  jdk = pkgs.jdk21;

  src = pkgs.fetchurl {
    url = "https://binaries.sonarsource.com/Distribution/sonarqube/sonarqube-${version}.zip";
    sha256 = "YBNnqX36z30LpU4j6lTXe97vVIzRtafyN4qD7qkx76E=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "sonarqube";
    inherit version;
    meta = {
      description = "Continuous inspection of code quality and security";
    };

    inherit src;
    nativeBuildInputs = [ pkgs.unzip ];

    unpackPhase = ''
      unzip $src
      mv sonarqube-${version} source
      sourceRoot=source
    '';

    dontBuild = true;

    buildInputs = [ jdk ];

    installPhase = ''
      mkdir -p $out/app $out/bin
      cp -r . $out/app/

      cat > $out/bin/sonarqube << 'WRAPPER'
#!/bin/sh
set -e

export JAVA_HOME=__JDK__
export SONAR_JAVA_PATH=__JDK__/bin/java
PORT="''${PORT:-9000}"

# Lazy copy the nixpkgs tree into $PWD/.sonarqube-home on first
# launch. Subsequent restarts reuse the existing copy (marker file).
HOME_DIR="$PWD/.sonarqube-home"
if [ ! -f "$HOME_DIR/.hop3-ready" ]; then
  rm -rf "$HOME_DIR"
  # -rL dereferences symlinks so we can chmod real files.
  cp -rL --no-preserve=ownership __APPDIR__/. "$HOME_DIR"
  chmod -R u+w "$HOME_DIR"
  touch "$HOME_DIR/.hop3-ready"
fi

# Writable data/logs/temp/extensions live in $PWD alongside the
# sonarqube-home copy — the JVM argv below points sonar at them.
mkdir -p data logs temp extensions

# sonar.properties goes into the writable home's conf dir so
# sonar.sh finds it at the expected relative path.
cat > "$HOME_DIR/conf/sonar.properties" << CONFEOF
sonar.jdbc.url=jdbc:postgresql://''${PGHOST:-localhost}:''${PGPORT:-5432}/''${PGDATABASE:-sonarqube}
sonar.jdbc.username=''${PGUSER:-sonarqube}
sonar.jdbc.password=''${PGPASSWORD:-}
sonar.web.host=''${BIND_ADDRESS:-0.0.0.0}
sonar.web.port=''${PORT}
sonar.path.data=$PWD/data
sonar.path.logs=$PWD/logs
sonar.path.temp=$PWD/temp
sonar.search.javaAdditionalOpts=''${SONAR_SEARCH_JAVAADDITIONALOPTS:--Dnode.store.allow_mmap=false}
CONFEOF

# Exec out of the writable copy so sonar.sh's readlink-based
# self-resolution lands inside $HOME_DIR, not the nix store.
exec "$HOME_DIR/bin/linux-x86-64/sonar.sh" console "$@"
WRAPPER
      sed -i "s|__JDK__|${jdk}|g" $out/bin/sonarqube
      sed -i "s|__APPDIR__|$out/app|g" $out/bin/sonarqube
      chmod +x $out/bin/sonarqube

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/sonarqube"
  },
  "env": {
    "SONAR_SEARCH_JAVAADDITIONALOPTS": "-Dnode.store.allow_mmap=false"
  },
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

  env = {
    SONAR_SEARCH_JAVAADDITIONALOPTS = "-Dnode.store.allow_mmap=false";
  };
}
