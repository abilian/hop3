# hop3.nix - Nix expression for HedgeDoc deployment
#
# Uses the pre-built HedgeDoc release tarball (includes node_modules).
# Building from source with npm takes 10+ minutes — use the release instead.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "1.9.9";
  nodejs = pkgs.nodejs_22;

  src = pkgs.fetchurl {
    url = "https://github.com/hedgedoc/hedgedoc/releases/download/${version}/hedgedoc-${version}.tar.gz";
    sha256 = "F2nTDmBFgEBHWm109TlSEBlixAw5B2Xhnm/28/5wwAg=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "hedgedoc";
    inherit version;
    meta.description = "Real-time collaborative markdown editor";

    inherit src;
    sourceRoot = "hedgedoc";

    # Pre-built release — no build needed
    dontBuild = true;
    # Release tarball may have broken dev-dep symlinks
    dontFixup = true;

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3

      cp -r . $out/app/

      # Create wrapper that generates config.json and starts HedgeDoc
      cat > $out/bin/hedgedoc << 'WRAPPER'
#!/bin/sh
export NODE_ENV=production
export NODE_PATH=APPDIR/node_modules

PORT="''${PORT:-8080}"

# HedgeDoc reads config.json from cwd. Create a writable working directory
# with symlinks to the Nix store app contents.
for item in app.js lib node_modules public docs locales; do
  if [ -e APPDIR/$item ] && [ ! -e $item ]; then
    ln -sf APPDIR/$item $item
  fi
done

# HedgeDoc can be configured via environment variables (CMD_ prefix)
export CMD_PORT="$PORT"
export CMD_HOST="0.0.0.0"
export CMD_DB_URL="postgres://''${PGUSER:-hedgedoc}:''${PGPASSWORD:-}@''${PGHOST:-localhost}:''${PGPORT:-5432}/''${PGDATABASE:-hedgedoc}"
export CMD_SESSION_SECRET="''${CMD_SESSION_SECRET:-$(head -c 32 /dev/urandom | base64)}"
export CMD_ALLOW_ANONYMOUS=true
export CMD_ALLOW_ANONYMOUS_EDITS=true
export CMD_DEFAULT_PERMISSION=freely

exec NODEPATH/node app.js
WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/hedgedoc
      sed -i "s|NODEPATH|${nodejs}/bin|g" $out/bin/hedgedoc
      chmod +x $out/bin/hedgedoc

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/hedgedoc"
  },
  "env": {
    "NODE_ENV": "production"
  },
  "path": [
    "$out/bin",
    "${nodejs}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;
  env = { NODE_ENV = "production"; };
}
