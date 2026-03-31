# hop3.nix - Nix expression for CryptPad deployment
#
# Downloads the pre-built CryptPad release (includes node_modules).
# Building from source with npm inside Nix is impractical due to the
# large dependency tree and network requirements.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "5.7.0";
  nodejs = pkgs.nodejs;

  # Use the GitHub source archive (no pre-built release tarball available)
  src = pkgs.fetchurl {
    url = "https://github.com/cryptpad/cryptpad/archive/refs/tags/${version}.tar.gz";
    sha256 = "h88JHy0PJrxNLfU0YLreeeOw0YBN/m7x5ZLOsmVM0h8=";
  };

  app = pkgs.stdenv.mkDerivation {
    # Allow network access during build (npm/composer/pip install)
    __noChroot = true;
    pname = "cryptpad";
    inherit version;
    meta.description = "End-to-end encrypted collaboration suite";

    inherit src;
    sourceRoot = "cryptpad-${version}";

    nativeBuildInputs = [ nodejs ];

    # Pre-built release — no build needed
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/

      # Install production dependencies only
      cd $out/app
      export HOME=$TMPDIR
      ${nodejs}/bin/npm install --production --legacy-peer-deps 2>/dev/null || true

      cat > $out/bin/cryptpad << EOF
#!/bin/sh
cd $out/app
exec ${nodejs}/bin/node server.js "\$@"
EOF
      chmod +x $out/bin/cryptpad

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/cryptpad"
  },
  "env": {
    "CPAD_MAIN_DOMAIN": "http://localhost:8080"
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
  env = {
    CPAD_MAIN_DOMAIN = "http://localhost:8080";
  };
}
