# hop3.nix - Nix expression for WriteFreely deployment
#
# WriteFreely's binary expects to find `templates/`, `pages/`, and
# `static/` directories relative to the binary (it checks
# $exe_dir/../share/writefreely/...). The nixpkgs `writefreely`
# derivation ships only the binary and omits these assets, so we
# fetch the upstream release tarball separately and wire the asset
# directories into config.ini at runtime.
#
# This is a hybrid: the binary comes from nixpkgs (compiled
# reproducibly), the static assets come from the upstream prebuilt
# release. A pure Tier-1 packaging would require nixpkgs to ship the
# full $out/share/writefreely tree; until that lands, this is the
# pragmatic middle ground.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  writefreely = pkgs.writefreely;

  wfRelease = pkgs.fetchurl {
    url = "https://github.com/writefreely/writefreely/releases/download/v0.16.0/writefreely_0.16.0_linux_amd64.tar.gz";
    sha256 = "4626c2998f4cdad3390452f0e18950ccd0a2d3b6e3595e45a40db6df0a2defa5";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "writefreely";
    version = writefreely.version;
    meta = {
      description = "Minimalist federated blog platform";
    };

    dontUnpack = true;
    dontBuild = true;
    nativeBuildInputs = [ pkgs.gnutar pkgs.gzip ];

    installPhase = ''
      mkdir -p $out/bin $out/hop3 $out/share/writefreely

      # Unpack the upstream tarball for its templates/, pages/, static/.
      # The tarball also includes a `writefreely` binary which we ignore
      # in favour of the nixpkgs-built one.
      tar xzf ${wfRelease} -C $out/share/writefreely --strip-components=1

      cat > $out/bin/writefreely-wrapper << 'WRAPPER'
      #!/bin/sh
      set -e

      mkdir -p data

      PORT="''${PORT:-8080}"

      cat > config.ini << EOF
      [server]
      port                 = ''${PORT}
      bind                 = 0.0.0.0
      hash_seed            = $(head -c 32 /dev/urandom | base64)
      templates_parent_dir = PLACEHOLDER_SHARE
      static_parent_dir    = PLACEHOLDER_SHARE
      pages_parent_dir     = PLACEHOLDER_SHARE

      [database]
      type     = sqlite3
      filename = data/writefreely.db

      [app]
      site_name      = WriteFreely
      host           = http://localhost:''${PORT}
      theme          = write
      federation     = true
      local_timeline = true
      EOF

      if [ ! -f data/writefreely.db ]; then
        ${writefreely}/bin/writefreely --init-db || true
        ${writefreely}/bin/writefreely --gen-keys || true
      fi

      exec ${writefreely}/bin/writefreely
      WRAPPER

      # Interpolate the Nix-store share path into the wrapper
      sed -i "s|PLACEHOLDER_SHARE|$out/share/writefreely|g" $out/bin/writefreely-wrapper
      chmod +x $out/bin/writefreely-wrapper

      cat > $out/hop3/runtime.json << EOF
      {
        "workers": {
          "web": "$out/bin/writefreely-wrapper"
        },
        "env": {},
        "path": [
          "$out/bin",
          "${writefreely}/bin"
        ]
      }
      EOF
    '';
  };

in
{
  package = app;
  env = {};
}
