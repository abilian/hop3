# hop3.nix - Nix expression for the Hop3 landing page
#
# Demonstrates the "static" worker pattern: nginx serves files directly
# from the Nix store, no backend process. The hop3 deployer detects
# the static-only worker in runtime.json and configures nginx
# accordingly (StaticDeployer in plugins/deploy/static/).

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  app = pkgs.stdenv.mkDerivation {
    pname = "hop3-landing";
    version = "0.1.0";
    meta.description = "Hop3 landing page (static-site Nix worker reference app)";

    src = ./.;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/public $out/hop3

      cp -r public/* $out/public/

      # Static worker: nginx serves directly from $out/public.
      # No "web", "wsgi", or "cron" workers — only "static".
      # The Hop3 StaticDeployer will pick this up and configure nginx.
      cat > $out/hop3/runtime.json <<EOF
{
  "workers": {
    "static": "$out/public"
  },
  "env": {}
}
EOF
    '';
  };

in {
  package = app;
  env = {};
}
