# hop3.nix - Nix expression for Isso deployment
#
# Isso is not in nixpkgs python3Packages, so we install it via pip.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  python = pkgs.python3;
  version = "0.13.1.dev0";

  app = pkgs.stdenv.mkDerivation {
    pname = "isso";
    inherit version;
    __noChroot = true;  # pip install needs network
    meta.description = "A lightweight commenting system, Disqus alternative";

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ python pkgs.python3Packages.pip ];

    installPhase = ''
      mkdir -p $out/app $out/bin $out/venv $out/hop3

      # Create virtualenv and install isso
      ${python}/bin/python -m venv $out/venv
      $out/venv/bin/pip install isso gunicorn 2>/dev/null

      cat > $out/bin/isso-start << 'EOF'
#!/bin/sh
set -e
mkdir -p data

# Isso has no admin USERNAME — the password is the whole credential — so it must
# be present or the moderation dashboard is not protected at all. Refuse to
# start rather than serve it open.
: "''${ADMIN_PASSWORD:?isso: ADMIN_PASSWORD not injected — refusing to serve an unprotected moderation dashboard}"

# `host` and `public-endpoint` are what isso tells the BROWSER, so they must be
# the public address, not the loopback the server binds.
cat > isso-runtime.cfg << CFGEOF
[general]
dbpath = data/comments.db
host = ''${HOP3_PUBLIC_URL:-http://localhost:''${PORT:-8080}}

[server]
listen = http://''${BIND_ADDRESS:-0.0.0.0}:''${PORT:-8080}
public-endpoint = ''${HOP3_PUBLIC_URL:-http://localhost:''${PORT:-8080}}

# Absent this section isso serves /admin/ disabled, and the smoke test said so:
# "the admin dashboard is not asking for a password" — correct, there was no
# dashboard to ask.
[admin]
enabled = true
password = ''${ADMIN_PASSWORD}

# Hold new comments for approval. Without it any anonymous visitor
# self-publishes, which is isso's equivalent of open registration.
[moderation]
enabled = true
CFGEOF
exec VENV/bin/isso -c isso-runtime.cfg "$@"
EOF
      sed -i "s|VENV|$out/venv|g" $out/bin/isso-start
      chmod +x $out/bin/isso-start

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/isso-start"
  },
  "env": {},
  "path": ["$out/bin", "$out/venv/bin"]
}
EOF
    '';
  };

in { package = app; }
