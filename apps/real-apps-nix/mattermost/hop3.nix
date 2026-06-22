# hop3.nix - Nix expression for Mattermost deployment
#
# Wraps the nixpkgs mattermost package (built from source by nixpkgs)
# with a startup wrapper that generates configuration and starts the server.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  mattermost = pkgs.mattermost;

  app = pkgs.stdenv.mkDerivation {
    pname = "mattermost";
    version = mattermost.version;
    meta = {
      description = "Open source team collaboration platform";
    };

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

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

exec ${mattermost}/bin/mattermost
WRAPPER
      sed -i "s|SHAREDIR|${mattermost}/share/mattermost|g" $out/bin/mattermost-wrapper
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
    "$out/bin",
    "${mattermost}/bin"
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
