# hop3.nix - Nix expression for Matrix Synapse deployment
#
# Installs matrix-synapse via pip into a venv. Requires Rust (for
# cryptography) and native build tools for C extensions at build time.
#
# Two runtime needs that the wrapper handles explicitly:
#
#   1. LD_LIBRARY_PATH — Synapse's dependency chain (Pillow, matrix-zstd
#      support) loads libzstd / libjpeg-turbo dynamically. Pillow wheels
#      vendor their native libs under `pillow.libs/` inside site-packages;
#      libzstd we take from ${pkgs.zstd}/lib.
#
#   2. Bind port — Synapse's `--generate-config` emits a `homeserver.yaml`
#      whose client listener hardcodes `port: 8008` and binds to 127.0.0.1
#      + ::1. Hop3 assigns a dynamic $PORT and expects the app to listen
#      there. We sed the generated yaml on first run to match.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

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
      # psycopg2-binary (pre-compiled) — avoids needing pg_config at build.
      $out/venv/bin/pip install matrix-synapse psycopg2-binary

      cat > $out/bin/synapse-start << 'WRAPPER'
#!/bin/sh
set -e

mkdir -p data media_store

# LD_LIBRARY_PATH — Synapse loads libzstd + Pillow's vendored libs at
# runtime. Pillow wheels vendor their native deps under pillow.libs/;
# libzstd comes from the Nix store explicitly.
SITE_PKGS=$(find __VENV__/lib -name "site-packages" -type d 2>/dev/null | head -1)
PILLOW_LIBS="$SITE_PKGS/pillow.libs"
export LD_LIBRARY_PATH="$PILLOW_LIBS:$SITE_PKGS:__ZSTDLIB__:''${LD_LIBRARY_PATH:-}"

# First-run config generation.
if [ ! -f homeserver.yaml ]; then
  __VENV__/bin/synapse_homeserver \
    --server-name "''${SERVER_NAME:-localhost}" \
    --config-path homeserver.yaml \
    --generate-config \
    --report-stats=no || true
fi

# Apply Hop3 runtime overrides to the client listener on every start
# (PORT is assigned per-deploy, so we can't bake it in at --generate-config
# time). Use Python yaml rather than sed so we don't depend on the exact
# indentation Synapse happens to emit this release.
if [ -f homeserver.yaml ]; then
  PORT="''${PORT:-8008}" __VENV__/bin/python - <<'PYFIX'
import os, yaml
port = int(os.environ.get("PORT", 8008))
with open("homeserver.yaml") as f:
    cfg = yaml.safe_load(f) or {}
listeners = cfg.get("listeners") or []
for listener in listeners:
    if listener.get("type") == "http":
        listener["port"] = port
        listener["bind_addresses"] = ["127.0.0.1"]
cfg["listeners"] = listeners
with open("homeserver.yaml", "w") as f:
    yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
PYFIX
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
