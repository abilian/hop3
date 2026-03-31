# hop3.nix - Nix expression for SearXNG deployment
#
# Uses the nixpkgs searxng package or builds from source with Python.

{ pkgs ? import <nixpkgs> {} }:

let
  pythonEnv = pkgs.python3.withPackages (ps: with ps; [
    flask
    babel
    certifi
    lxml
    httpx
    httpx-socks
    pyyaml
    pygments
    redis
    setproctitle
    uvloop
  ]);

  app = pkgs.stdenv.mkDerivation {
    # Allow network access during build (npm/composer/pip install)
    __noChroot = true;
    pname = "searxng";
    version = "2024";
    meta = {
      description = "Privacy-respecting, hackable metasearch engine";
    };

    src = pkgs.fetchFromGitHub {
      owner = "searxng";
      repo = "searxng";
      rev = "master";
      sha256 = "sdvKQz3UcJ4pFWvtGfgaXWtu3svYZbKHeebtn36qAzo=";
    };

    buildInputs = [ pythonEnv ];

    buildPhase = ''
      export HOME=$TMPDIR
      ${pythonEnv}/bin/python -m pip install --no-build-isolation --prefix=$TMPDIR/pip-out . || true
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/

      cat > $out/bin/searxng << 'EOF'
#!/bin/sh
cd $out/app
exec ${pythonEnv}/bin/python -m searx.webapp "$@"
EOF
      chmod +x $out/bin/searxng

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/searxng"
  },
  "env": {
    "SEARXNG_BASE_URL": "http://localhost:8080",
    "SEARXNG_SECRET": "change-me-to-random-string"
  },
  "path": [
    "$out/bin",
    "${pythonEnv}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;

  env = {
    SEARXNG_BASE_URL = "http://localhost:8080";
    SEARXNG_SECRET = "change-me-to-random-string";
  };
}
