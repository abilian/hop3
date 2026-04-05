"""Mattermost: tar.gz archive, large JSON config, symlink-from-store pattern."""

from hop3_nix_gen.spec import AppSpec, ConfigFile, FileMapping, Source

# The symlink loop copes with Mattermost's requirement that i18n/, templates/,
# fonts/, client/ are present in the cwd but those directories live in the
# read-only Nix store. We symlink them into the writable cwd.
_SYMLINK_LOOP = """# Symlink Mattermost assets from Nix store into working directory
for item in SHAREDIR/*; do
  base="$(basename "$item")"
  if [ ! -e "$base" ]; then
    ln -sf "$item" "$base"
  fi
done"""

_CONFIG_JSON = """{
  "ServiceSettings": {
    "SiteURL": "${MM_SERVICESETTINGS_SITEURL:-http://localhost:${PORT}}",
    "ListenAddress": ":${PORT}",
    "ConnectionSecurity": "",
    "TLSCertFile": "",
    "TLSKeyFile": "",
    "EnableLocalMode": false
  },
  "SqlSettings": {
    "DriverName": "postgres",
    "DataSource": "postgres://${PGUSER:-mattermost}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-mattermost}?sslmode=disable",
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
"""

SPEC = AppSpec(
    pname="mattermost",
    version="9.4.2",
    description="Open source team collaboration platform",
    template="prebuilt-archive",
    source=Source(
        url="https://releases.mattermost.com/${version}/mattermost-${version}-linux-amd64.tar.gz",
        sha256="e/1ZaogKFir/NR5Eel35es+CZAWp2YM1pByldNtjJuc=",
        unpack=True,
    ),
    source_root="mattermost",
    file_mappings=[
        FileMapping(source="bin/mattermost", destination="bin/", recursive=False),
        FileMapping(
            source="templates fonts i18n",
            destination="share/mattermost/",
            recursive=True,
        ),
        FileMapping(
            source="client", destination="share/mattermost/", recursive=True
        ),
    ],
    exec_target="mattermost",
    local_vars={
        "PORT": "${PORT:-8080}",
    },
    pre_exec_commands=[
        "mkdir -p data logs config plugins client/plugins",
        _SYMLINK_LOOP,
    ],
    config_files=[
        ConfigFile(
            path="config/config.json",
            format="raw",
            raw_content=_CONFIG_JSON,
        ),
    ],
    runtime_env={
        "MM_SERVICESETTINGS_SITEURL": "http://localhost:8080",
    },
)
