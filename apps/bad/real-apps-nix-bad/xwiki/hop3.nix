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

      cat > $out/bin/xwiki << 'WRAPPER'
#!/bin/sh
export JAVA_HOME=__JDK__
export XWIKI_NONINTERACTIVE=true
export JETTY_PORT=''${PORT:-8080}

# XWiki writes to data/, logs/, temp/, work/ — symlink the read-only
# Nix store tree into the writable cwd so Jetty can start.
for item in __APPDIR__/*; do
  name=$(basename "$item")
  [ -e "$name" ] || ln -sf "$item" "$name"
done

# Ensure writable dirs exist (XWiki/Jetty expects them)
mkdir -p data logs temp work webapps

exec bash ./start_xwiki.sh "$@"
WRAPPER
      sed -i "s|__JDK__|${jdk}|g" $out/bin/xwiki
      sed -i "s|__APPDIR__|$out/app|g" $out/bin/xwiki
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
