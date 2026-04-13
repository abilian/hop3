# hop3.nix - Nix expression for Matrix Synapse deployment
#
# Installs matrix-synapse via pip. Requires Rust (for cryptography) and
# native build tools for C extensions.

{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python3;

  app = pkgs.stdenv.mkDerivation {
    pname = "matrix-synapse";
    version = "1.x";
    __noChroot = true;  # pip install needs network
    meta.description = "Matrix homeserver implementation";

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [
      python
      pkgs.python3Packages.pip
      pkgs.rustc
      pkgs.cargo
      pkgs.pkg-config
      pkgs.openssl
      pkgs.libffi
      pkgs.zstd
    ];

    installPhase = ''
      mkdir -p $out/bin $out/venv $out/hop3

      # Cargo/maturin needs writable HOME and SSL certs
      export HOME=$TMPDIR
      export CARGO_HOME=$TMPDIR/.cargo
      export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
      export CARGO_HTTP_CAINFO=$SSL_CERT_FILE

      ${python}/bin/python -m venv $out/venv
      # Use psycopg2-binary (pre-compiled) to avoid needing pg_config
      $out/venv/bin/pip install matrix-synapse psycopg2-binary

      cat > $out/bin/synapse-start << 'WRAPPER'
#!/bin/sh
mkdir -p data media_store

# Set LD_LIBRARY_PATH to find native .so files.
# Pillow pip wheels vendor libzstd/libjpeg/etc. under pillow.libs/
SITE_PKGS=$(find __VENV__/lib -name "site-packages" -type d 2>/dev/null | head -1)
PILLOW_LIBS="$SITE_PKGS/pillow.libs"
export LD_LIBRARY_PATH="$PILLOW_LIBS:$SITE_PKGS:__ZSTDLIB__:''${LD_LIBRARY_PATH:-}"

# Generate homeserver.yaml on first run if missing
if [ ! -f homeserver.yaml ]; then
  __VENV__/bin/synapse_homeserver \
    --server-name "''${SERVER_NAME:-localhost}" \
    --config-path homeserver.yaml \
    --generate-config \
    --report-stats=no 2>/dev/null || true
  # Patch the generated config for Hop3
  if [ -f homeserver.yaml ]; then
    sed -i "s|^#.*listeners:|listeners:|" homeserver.yaml
  fi
fi

exec __VENV__/bin/synapse_homeserver \
  --config-path homeserver.yaml \
  "$@"
WRAPPER
      sed -i "s|__VENV__|$out/venv|g" $out/bin/synapse-start
      sed -i "s|__ZSTDLIB__|${pkgs.zstd.out}/lib|g" $out/bin/synapse-start
      chmod +x $out/bin/synapse-start

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/synapse-start"
  },
  "env": {
    "SERVER_NAME": "localhost"
  },
  "path": ["$out/bin", "$out/venv/bin"]
}
EOF
    '';
  };

in { package = app; }
