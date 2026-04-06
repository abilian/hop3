"""Focalboard: tar.gz archive, JSON config, PostgreSQL backend."""

from hop3_nix_gen.spec import AppSpec, ConfigFile, FileMapping, Source

_CONFIG_JSON = """{
  "serverRoot": "http://localhost:${PORT}",
  "port": ${PORT},
  "dbtype": "postgres",
  "dbconfig": "postgres://${PGUSER:-focalboard}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-focalboard}?sslmode=disable",
  "postgres_dbconfig": "postgres://${PGUSER:-focalboard}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-focalboard}?sslmode=disable",
  "webpath": "SHAREDIR/webapp-pack",
  "filespath": "./files",
  "telemetry": false,
  "session_expire_time": 2592000,
  "session_refresh_time": 18000,
  "localOnly": false,
  "enableLocalMode": true,
  "localModeSocketLocation": "/var/tmp/focalboard_local.socket"
}
"""

SPEC = AppSpec(
    pname="focalboard",
    version="7.10.5",
    description="Open source project management tool",
    template="prebuilt-archive",
    source=Source(
        url="https://github.com/mattermost-community/focalboard/releases/download/v${version}/focalboard-server-linux-amd64.tar.gz",
        sha256="VZFQqC5QwR/gy6/RKtA55kuIUMer8hGYdZi9otDxiAQ=",
        archive="tar-gz",
    ),
    source_root=".",
    file_mappings=[
        FileMapping(
            source="focalboard/bin/focalboard-server",
            destination="bin/",
            recursive=True,
        ),
        FileMapping(
            source="focalboard/pack",
            destination="share/focalboard/webapp-pack",
            recursive=True,
        ),
    ],
    exec_target="focalboard-server",
    local_vars={
        "PORT": "${PORT:-8080}",
    },
    pre_exec_commands=[
        "mkdir -p files",
    ],
    config_files=[
        ConfigFile(
            path="config.json",
            format="raw",
            raw_content=_CONFIG_JSON,
        ),
    ],
    runtime_env={
        "FOCALBOARD_EDITION": "personal",
    },
)
