# hop3.nix - Nix expression for the Hop3 landing page
#
# Demonstrates the "static" worker pattern: nginx serves files directly
# from the Nix store, no backend process. The hop3 deployer detects
# the static-only worker in runtime.json and configures nginx
# accordingly (StaticDeployer in plugins/deploy/static/).

{ pkgs ? import <nixpkgs> {} }:

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
