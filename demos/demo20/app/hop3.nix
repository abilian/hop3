# hop3.nix — hand-written Nix expression (the "custom Nix" path).
#
# You write the full expression; Hop3's NixBuilder runs `nix-build` and reads
# $out/hop3/runtime.json for the worker command, env, and PATH. Here we build a
# tiny static site and serve it with Python's stdlib http.server.

{ pkgs ? import <nixpkgs> { } }:

let
  python = pkgs.python3;

  app = pkgs.stdenv.mkDerivation {
    pname = "demo20-nix-custom";
    version = "0.1.0";
    meta.description = "Static site built from a hand-written hop3.nix";

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/app $out/bin $out/hop3

      cat > $out/app/index.html << 'HTML'
<!doctype html>
<title>Hop3 — Custom Nix</title>
<h1>Hello from a custom Nix deployment</h1>
<p>This page was built from a hand-written hop3.nix expression.</p>
HTML

      cat > $out/bin/serve << 'WRAPPER'
#!/bin/sh
exec ${python}/bin/python3 -m http.server "''${PORT:-8080}" --bind 0.0.0.0 --directory $out/app
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/serve
      chmod +x $out/bin/serve

      cat > $out/hop3/runtime.json << EOF
{
  "workers": { "web": "$out/bin/serve" },
  "env": {},
  "path": [ "$out/bin", "${python}/bin" ]
}
EOF
    '';
  };
in
{
  package = app;
  env = { };
}
