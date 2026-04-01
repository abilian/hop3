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
      # Install searxng into a dedicated Python venv so the module is importable
      ${pythonEnv}/bin/python -m venv $TMPDIR/venv --system-site-packages
      $TMPDIR/venv/bin/pip install --no-build-isolation . || true
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin $out/venv

      cp -r . $out/app/
      cp -r $TMPDIR/venv/* $out/venv/

      cat > $out/bin/searxng << 'WRAPPER'
#!/bin/sh
# Add the installed searxng source to PYTHONPATH so 'searx' module is found
export PYTHONPATH="APPDIR:''${PYTHONPATH:-}"

# SearXNG settings
mkdir -p settings
if [ ! -f settings/settings.yml ]; then
  if [ -f APPDIR/searx/settings.yml ]; then
    cp APPDIR/searx/settings.yml settings/settings.yml
  fi
fi
export SEARXNG_SETTINGS_PATH="$PWD/settings/settings.yml"

exec PYTHONBIN/python -m searx.webapp "$@"
WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/searxng
      sed -i "s|PYTHONBIN|$out/venv/bin|g" $out/bin/searxng
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
    "$out/venv/bin",
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
