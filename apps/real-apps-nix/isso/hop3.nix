# hop3.nix - Nix expression for Isso deployment
#
# Isso is not in nixpkgs python3Packages, so we install it via pip.

{ pkgs ? import <nixpkgs> {} }:

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

      # Default config
      cat > $out/app/isso.cfg << 'ISSOEOF'
[general]
dbpath = data/comments.db
host = http://localhost:8080

[server]
listen = http://0.0.0.0:8080
ISSOEOF

      cat > $out/bin/isso-start << 'EOF'
#!/bin/sh
mkdir -p data
# Generate config with the correct port at runtime
cat > isso-runtime.cfg << CFGEOF
[general]
dbpath = data/comments.db
host = http://localhost:''${PORT:-8080}

[server]
listen = http://''${BIND_ADDRESS:-0.0.0.0}:''${PORT:-8080}
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
