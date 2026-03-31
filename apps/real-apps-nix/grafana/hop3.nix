# hop3.nix - Nix expression for Grafana deployment
#
# Downloads the pre-built Grafana release and creates a wrapper
# that generates configuration and starts the server.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "11.3.2";

  grafana-release = pkgs.fetchurl {
    url = "https://dl.grafana.com/oss/release/grafana-${version}.linux-amd64.tar.gz";
    sha256 = "+q0bQKTrx8q+pHmxVSqB894QwD2lsoGTz6QaeT52FVc=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "grafana";
    inherit version;
    meta = {
      description = "The open and composable observability and data visualization platform";
    };

    src = grafana-release;
    sourceRoot = "grafana-v${version}";

    installPhase = ''
      mkdir -p $out/bin $out/hop3 $out/share/grafana

      # Install the server binary and default config
      cp bin/grafana-server $out/bin/
      cp -r conf public $out/share/grafana/

      # Create wrapper script that generates config and starts grafana
      cat > $out/bin/grafana-wrapper << 'WRAPPER'
#!/bin/sh
PORT="''${PORT:-8080}"

mkdir -p data logs conf/provisioning/datasources conf/provisioning/dashboards

# Create minimal config if not present
if [ ! -f conf/custom.ini ]; then
  cat > conf/custom.ini << EOF
[server]
http_port = ''${PORT}

[paths]
data = data
logs = logs

[security]
admin_user = ''${GF_SECURITY_ADMIN_USER:-admin}
EOF
fi

export GF_SERVER_HTTP_PORT="''${PORT}"
export GF_PATHS_DATA="./data"
export GF_PATHS_LOGS="./logs"
export GF_PATHS_PROVISIONING="./conf/provisioning"

exec BINDIR/grafana-server \
  --homepath SHAREDIR \
  --config ./conf/custom.ini
WRAPPER
      sed -i "s|BINDIR|$out/bin|g" $out/bin/grafana-wrapper
      sed -i "s|SHAREDIR|$out/share/grafana|g" $out/bin/grafana-wrapper
      chmod +x $out/bin/grafana-wrapper

      # Write runtime metadata for Hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/grafana-wrapper"
  },
  "env": {
    "GF_SECURITY_ADMIN_USER": "admin",
    "GF_PATHS_DATA": "./data",
    "GF_PATHS_LOGS": "./logs"
  },
  "path": [
    "$out/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;

  env = {
    GF_SECURITY_ADMIN_USER = "admin";
    GF_PATHS_DATA = "./data";
    GF_PATHS_LOGS = "./logs";
  };
}
