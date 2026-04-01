# hop3.nix - Nix expression for Mattermost deployment
#
# Downloads the pre-built Mattermost release and creates a wrapper
# that generates configuration and starts the server.

{ pkgs ? import <nixpkgs> {} }:

let
  version = "9.4.2";

  mattermost-release = pkgs.fetchurl {
    url = "https://releases.mattermost.com/${version}/mattermost-${version}-linux-amd64.tar.gz";
    sha256 = "e/1ZaogKFir/NR5Eel35es+CZAWp2YM1pByldNtjJuc=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "mattermost";
    inherit version;
    meta = {
      description = "Open source team collaboration platform";
    };

    src = mattermost-release;
    sourceRoot = "mattermost";

    installPhase = ''
      mkdir -p $out/bin $out/hop3 $out/share/mattermost

      # Install server binary and assets
      cp bin/mattermost $out/bin/
      cp -r templates fonts i18n $out/share/mattermost/ || true
      cp -r client $out/share/mattermost/ || true

      # Create wrapper script that generates config and starts mattermost
      cat > $out/bin/mattermost-wrapper << 'WRAPPER'
#!/bin/sh
PORT="''${PORT:-8080}"

mkdir -p data logs config plugins client/plugins

# Symlink Mattermost assets from Nix store into working directory
# Mattermost expects i18n/, templates/, fonts/, client/ in cwd
for item in SHAREDIR/*; do
  base="$(basename "$item")"
  if [ ! -e "$base" ]; then
    ln -sf "$item" "$base"
  fi
done

# Generate configuration
cat > config/config.json << CONFEOF
{
  "ServiceSettings": {
    "SiteURL": "''${MM_SERVICESETTINGS_SITEURL:-http://localhost:''${PORT}}",
    "ListenAddress": ":''${PORT}",
    "ConnectionSecurity": "",
    "TLSCertFile": "",
    "TLSKeyFile": "",
    "EnableLocalMode": false
  },
  "SqlSettings": {
    "DriverName": "postgres",
    "DataSource": "postgres://''${PGUSER:-mattermost}:''${PGPASSWORD:-}@''${PGHOST:-localhost}:''${PGPORT:-5432}/''${PGDATABASE:-mattermost}?sslmode=disable",
    "MaxIdleConns": 20,
    "MaxOpenConns": 300,
    "Trace": false,
    "AtRestEncryptKey": "$(head -c 32 /dev/urandom | base64)",
    "QueryTimeout": 30
  },
  "LogSettings": {
    "EnableConsole": true,
    "ConsoleLevel": "INFO",
    "EnableFile": false
  },
  "FileSettings": {
    "DriverName": "local",
    "Directory": "./data/"
  },
  "EmailSettings": {
    "SendEmailNotifications": false,
    "RequireEmailVerification": false
  },
  "PluginSettings": {
    "Enable": true,
    "Directory": "./plugins",
    "ClientDirectory": "./client/plugins"
  }
}
CONFEOF

exec BINDIR/mattermost
WRAPPER
      sed -i "s|BINDIR|$out/bin|g" $out/bin/mattermost-wrapper
      sed -i "s|SHAREDIR|$out/share/mattermost|g" $out/bin/mattermost-wrapper
      chmod +x $out/bin/mattermost-wrapper

      # Write runtime metadata for Hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/mattermost-wrapper"
  },
  "env": {
    "MM_SERVICESETTINGS_SITEURL": "http://localhost:8080"
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
    MM_SERVICESETTINGS_SITEURL = "http://localhost:8080";
  };
}
