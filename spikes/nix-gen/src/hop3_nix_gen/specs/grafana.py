"""Grafana: tar.gz archive, INI config, multiple env exports."""

from hop3_nix_gen.spec import AppSpec, ConfigFile, FileMapping, Source

SPEC = AppSpec(
    pname="grafana",
    version="11.3.2",
    description=(
        "The open and composable observability and data visualization platform"
    ),
    template="prebuilt-archive",
    source=Source(
        url="https://dl.grafana.com/oss/release/grafana-${version}.linux-amd64.tar.gz",
        sha256="+q0bQKTrx8q+pHmxVSqB894QwD2lsoGTz6QaeT52FVc=",
        unpack=True,
    ),
    source_root="grafana-v${version}",
    file_mappings=[
        FileMapping(source="bin/*", destination="bin/", recursive=True),
        FileMapping(source="conf", destination="share/grafana/", recursive=True),
        FileMapping(source="public", destination="share/grafana/", recursive=True),
    ],
    exec_target="grafana",
    exec_args=[
        "server",
        "--homepath",
        "SHAREDIR",
        "--config",
        '"$PWD/conf/custom.ini"',
    ],
    local_vars={
        "PORT": "${PORT:-8080}",
    },
    env_exports={
        "GF_SERVER_HTTP_PORT": "${PORT}",
        "GF_PATHS_DATA": "$PWD/data",
        "GF_PATHS_LOGS": "$PWD/logs",
        "GF_PATHS_PROVISIONING": "$PWD/conf/provisioning",
    },
    pre_exec_commands=[
        "mkdir -p data logs conf/provisioning/datasources conf/provisioning/dashboards",
    ],
    config_files=[
        ConfigFile(
            path="conf/custom.ini",
            format="ini",
            create_if_missing=True,
            sections={
                "server": {
                    "http_port": "${PORT}",
                },
                "paths": {
                    "data": "data",
                    "logs": "logs",
                },
                "security": {
                    "admin_user": "${GF_SECURITY_ADMIN_USER:-admin}",
                },
            },
        ),
    ],
    runtime_env={
        "GF_SECURITY_ADMIN_USER": "admin",
        "GF_PATHS_DATA": "./data",
        "GF_PATHS_LOGS": "./logs",
    },
)
