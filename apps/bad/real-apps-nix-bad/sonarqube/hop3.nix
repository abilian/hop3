# hop3.nix - Nix expression for SonarQube deployment
#
# Downloads the SonarQube distribution zip and runs with JDK.

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
export JAVA_HOME=__JDK__
export SONAR_JAVA_PATH=__JDK__/bin/java
PORT="''${PORT:-9000}"

# Symlink the read-only SonarQube tree into the writable cwd
for item in __APPDIR__/*; do
  name=$(basename "$item")
  [ -e "$name" ] || ln -sf "$item" "$name"
done

# Create writable directories that SonarQube needs
mkdir -p data logs temp extensions conf

# Write sonar.properties configuration
cat > conf/sonar.properties << CONFEOF
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

exec ./bin/linux-x86-64/sonar.sh console "$@"
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
