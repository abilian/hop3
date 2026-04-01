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

# Set LD_LIBRARY_PATH to find bundled .so files (e.g., libzstd from pip wheels)
VENV_LIB=$(find VENV/lib -name "site-packages" -type d 2>/dev/null | head -1)
if [ -n "$VENV_LIB" ]; then
  export LD_LIBRARY_PATH="$VENV_LIB:ZSTDLIB:''${LD_LIBRARY_PATH:-}"
else
  export LD_LIBRARY_PATH="ZSTDLIB:''${LD_LIBRARY_PATH:-}"
fi

exec VENV/bin/synapse_homeserver \
  --server-name "''${SERVER_NAME:-localhost}" \
  --config-path homeserver.yaml \
  "$@"
WRAPPER
      sed -i "s|VENV|$out/venv|g" $out/bin/synapse-start
      sed -i "s|ZSTDLIB|${pkgs.zstd.out}/lib|g" $out/bin/synapse-start
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
