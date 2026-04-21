# hop3.nix - Nix expression for XWiki deployment
#
# Downloads the XWiki Jetty distribution and runs with JDK.
#
# XWiki's start_xwiki.sh resolves $0 to the Nix-store path at runtime
# (same class of problem as Keycloak — see apps/real-apps-nix/keycloak/
# hop3.nix). Jetty then looks for its `logs/` directory under that
# resolved path, which is read-only and missing the directory:
#
#   java.io.IOException: Log directory does not exist.
#   Path=/nix/store/.../xwiki-16.1.0/app/logs
#
# Fix (lazy cp to writable home): on first start we copy the (read-only)
# XWiki tree from the Nix store into a writable per-app home at
# $PWD/.xwiki-home and cd into it before invoking start_xwiki.sh. Jetty
# then resolves $0 to the writable copy, so data/, logs/, temp/, work/
# are all writable. Subsequent restarts reuse the existing copy.

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
set -e

export JAVA_HOME=__JDK__
export XWIKI_NONINTERACTIVE=true
export JETTY_PORT="''${PORT:-8080}"

# Lazy cp to writable home. First deploy pays the cost (XWiki tree is
# ~400MB); subsequent redeploys reuse the existing copy preserved in
# $PWD by Hop3 across redeploys.
HOME_DIR="$PWD/.xwiki-home"
if [ ! -f "$HOME_DIR/.hop3-ready" ]; then
  rm -rf "$HOME_DIR"
  cp -rL --no-preserve=ownership __APPDIR__/. "$HOME_DIR"
  chmod -R u+w "$HOME_DIR"
  mkdir -p "$HOME_DIR/data" "$HOME_DIR/logs" "$HOME_DIR/temp" "$HOME_DIR/work" "$HOME_DIR/webapps"
  touch "$HOME_DIR/.hop3-ready"
fi

cd "$HOME_DIR"
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
