# hop3.nix - Nix expression for Radicale deployment
#
# Radicale is available as a top-level nixpkgs package (not in python3Packages).

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  radicale = pkgs.radicale;

  # The `[admin]`/`[probe]` create commands write bcrypt hashes into the
  # htpasswd file, and they run OUTSIDE the wrapper — so a `python3` carrying
  # bcrypt has to be on the app's PATH in its own right.
  python = pkgs.python3.withPackages (ps: [ ps.bcrypt ]);

  app = pkgs.stdenv.mkDerivation {
    pname = "radicale";
    version = radicale.version;
    meta.description = "A simple CalDAV and CardDAV server";

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/radicale-start << 'WRAPPER'
#!/bin/sh
PORT="''${PORT:-8080}"

mkdir -p collections
# The htpasswd file must EXIST before Radicale reads its config, even empty:
# the accounts are written into it after this process starts.
touch users

# Rewritten on every start, deliberately. This file used to be generated once
# and left alone, so a deployment that had ever run with `type = none` kept
# serving without authentication for the rest of its life.
cat > config << EOF
[server]
hosts = 0.0.0.0:''${PORT}

# htpasswd, NOT ''${RADICALE_AUTH_TYPE:-none}. That indirection defaulted to
# `none` and nothing ever set it otherwise, so every deployment served every
# calendar and address book to anyone who asked. The smoke test caught it on
# the one assertion that could: "a WRONG password returned 200, not 401".
# There is no safe default here, so auth is spelled out.
[auth]
type = htpasswd
htpasswd_filename = users
htpasswd_encryption = bcrypt

[storage]
filesystem_folder = collections
EOF

exec RADICALE_BIN --config config "$@"
WRAPPER
      sed -i "s|RADICALE_BIN|${radicale}/bin/radicale|g" $out/bin/radicale-start
      chmod +x $out/bin/radicale-start

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/radicale-start"
  },
  "env": {},
  "path": ["$out/bin", "${radicale}/bin", "${python}/bin"]
}
EOF
    '';
  };

in { package = app; }
