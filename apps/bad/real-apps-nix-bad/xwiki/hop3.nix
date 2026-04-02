# hop3.nix - Nix expression for XWiki deployment
#
# Downloads the XWiki Jetty distribution and runs with JDK.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "16.1.0";
  jdk = pkgs.jdk17;

  src = pkgs.fetchurl {
    url = "https://maven.xwiki.org/releases/org/xwiki/platform/xwiki-platform-distribution-jetty-hsqldb/${version}/xwiki-platform-distribution-jetty-hsqldb-${version}.zip";
    sha256 = "qEER4sOdXSwAr36a20eaBaXsicU0+XmqfgkQfYx2ELo=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "xwiki";
    inherit version;
    meta = {
      description = "Advanced open source enterprise wiki with structured data support";
    };

    inherit src;
    nativeBuildInputs = [ pkgs.unzip ];

    unpackPhase = ''
      unzip $src
      mv xwiki-platform-distribution-jetty-hsqldb-${version} source
      sourceRoot=source
    '';

    dontBuild = true;

    buildInputs = [ jdk ];

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/
      chmod +x $out/app/start_xwiki*.sh $out/app/stop_xwiki*.sh || true

      cat > $out/bin/xwiki << 'EOF'
#!/bin/sh
export JAVA_HOME=${jdk}
export XWIKI_NONINTERACTIVE=true
cd $out/app
export JETTY_PORT=''${PORT:-8080}
exec bash ./start_xwiki.sh "$@"
EOF
      chmod +x $out/bin/xwiki

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/xwiki"
  },
  "env": {
    "JAVA_OPTS": "-Xmx1024m",
    "XWIKI_NONINTERACTIVE": "true"
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
    JAVA_OPTS = "-Xmx1024m";
    XWIKI_NONINTERACTIVE = "true";
  };
}
