# hop3.nix - Nix expression for Jenkins deployment
#
# Downloads the Jenkins WAR file and runs with JDK.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "2.541.2";
  jdk = pkgs.jdk17;

  jenkinsWar = pkgs.fetchurl {
    url = "https://get.jenkins.io/war-stable/${version}/jenkins.war";
    sha256 = "3J1TLlTUt+t9eO3NMheHbdSBG0nRo7ZuWZrUpkLVcZM=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "jenkins";
    inherit version;
    meta = {
      description = "The leading open source automation server for CI/CD";
    };

    dontUnpack = true;
    dontBuild = true;

    buildInputs = [ jdk ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/app/jenkins_home

      cp ${jenkinsWar} $out/app/jenkins.war

      cat > $out/bin/jenkins << 'WRAPPER'
#!/bin/sh
export JENKINS_HOME="''${JENKINS_HOME:-./jenkins_home}"
mkdir -p "$JENKINS_HOME"
exec JAVAPATH/java \
  $JAVA_OPTS \
  -jar WARPATH \
  --httpPort="''${PORT:-8080}" \
  "$@"
WRAPPER
      sed -i "s|JAVAPATH|${jdk}/bin|g" $out/bin/jenkins
      sed -i "s|WARPATH|$out/app/jenkins.war|g" $out/bin/jenkins
      chmod +x $out/bin/jenkins

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/jenkins"
  },
  "env": {
    "JENKINS_HOME": "./jenkins_home",
    "JAVA_OPTS": "-Djava.awt.headless=true -Djenkins.install.runSetupWizard=false"
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
    JENKINS_HOME = "./jenkins_home";
    JAVA_OPTS = "-Djava.awt.headless=true -Djenkins.install.runSetupWizard=false";
  };
}
