# hop3.nix - Nix expression for Etherpad deployment
#
# Downloads the Etherpad source tarball and builds with Node.js/pnpm.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "2.0.3";
  nodejs = pkgs.nodejs_22;
  pnpm = pkgs.nodePackages.pnpm;

  src = pkgs.fetchurl {
    url = "https://github.com/ether/etherpad-lite/archive/refs/tags/v${version}.tar.gz";
    sha256 = "bcGa3cgoCAZZD5qC1EJqiKjvd8eEH5n5elDWqmyezBo=";
  };

  app = pkgs.stdenv.mkDerivation {
    # Allow network access during build (pnpm install)
    __noChroot = true;
    pname = "etherpad";
    inherit version;
    meta.description = "Real-time collaborative document editor";

    inherit src;
    sourceRoot = "etherpad-lite-${version}";

    nativeBuildInputs = [ nodejs pnpm pkgs.python3 pkgs.pkg-config ];
    buildInputs = [ nodejs ];

    dontFixup = true;

    buildPhase = ''
      export HOME=$TMPDIR
      export CI=true
      bin/installDeps.sh || true
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3

      cp -r . $out/app/

      # Wrapper: stays in writable cwd, symlinks app, generates config
      cat > $out/bin/etherpad << 'WRAPPER'
#!/bin/sh
export NODE_ENV=production

# Symlink Etherpad app into writable working directory
for item in APPDIR/*; do
  name=$(basename "$item")
  [ "$name" = "settings.json" ] && continue
  [ -e "$name" ] || ln -sf "$item" "$name"
done

mkdir -p var

# Generate settings.json in writable cwd
cat > settings.json << SETTINGS
{
  "title": "Etherpad",
  "ip": "0.0.0.0",
  "port": ''${PORT:-8080},
  "dbType": "dirty",
  "dbSettings": { "filename": "var/dirty.db" },
  "defaultPadText": "Welcome to Etherpad!",
  "trustProxy": true,
  "loglevel": "INFO"
}
SETTINGS

# Run using pnpm from the symlinked directory
export PATH="APPDIR/node_modules/.bin:PNPMDIR:NODEDIR:$PATH"
exec PNPMDIR/pnpm run prod "$@"
WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/etherpad
      sed -i "s|PNPMDIR|${pnpm}/bin|g" $out/bin/etherpad
      sed -i "s|NODEDIR|${nodejs}/bin|g" $out/bin/etherpad
      chmod +x $out/bin/etherpad

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/etherpad"
  },
  "env": {
    "NODE_ENV": "production"
  },
  "path": [
    "$out/bin",
    "${nodejs}/bin",
    "${pnpm}/bin"
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
