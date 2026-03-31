# hop3.nix - Nix expression for SonarQube deployment
#
# Downloads the SonarQube distribution zip and runs with JDK.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "26.2.0.119303";
  jdk = pkgs.jdk17;

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

      cat > $out/bin/sonarqube << 'EOF'
#!/bin/sh
export JAVA_HOME=${jdk}
export SONAR_JAVA_PATH=${jdk}/bin/java
cd $out/app
exec ./bin/linux-x86-64/sonar.sh console "$@"
EOF
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
