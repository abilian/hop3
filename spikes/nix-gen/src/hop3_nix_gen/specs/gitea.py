"""Gitea: prebuilt Go binary with INI config, PostgreSQL backend."""

from hop3_nix_gen.spec import AppSpec, ConfigFile, Source

SPEC = AppSpec(
    pname="gitea",
    version="1.21.4",
    description="Self-hosted Git service",
    template="prebuilt-binary",
    binary_name="gitea",
    exec_args=["web"],
    source=Source(
        url="https://dl.gitea.io/gitea/${version}/gitea-${version}-linux-amd64",
        sha256="WKxZM2BGLQAAHisMlMhDoXF6pTFW8Pt30y5+V57jv6s=",
        executable=True,
    ),
    local_vars={
        "PORT": "${PORT:-8080}",
        "DB_HOST": "${PGHOST:-localhost}",
        "DB_PORT": "${PGPORT:-5432}",
        "DB_NAME": "${PGDATABASE:-gitea}",
        "DB_USER": "${PGUSER:-gitea}",
        "DB_PASS": "${PGPASSWORD:-}",
    },
    env_exports={
        "GITEA_WORK_DIR": "$PWD",
    },
    pre_exec_commands=[
        "mkdir -p custom/conf data",
    ],
    config_files=[
        ConfigFile(
            path="custom/conf/app.ini",
            format="ini",
            sections={
                "server": {
                    "HTTP_PORT": "${PORT}",
                    "ROOT_URL": "http://localhost:${PORT}/",
                },
                "database": {
                    "DB_TYPE": "postgres",
                    "HOST": "${DB_HOST}:${DB_PORT}",
                    "NAME": "${DB_NAME}",
                    "USER": "${DB_USER}",
                    "PASSWD": "${DB_PASS}",
                },
                "repository": {
                    "ROOT": "data/gitea-repositories",
                },
                "log": {
                    "MODE": "console",
                    "LEVEL": "Info",
                },
                "security": {
                    "INSTALL_LOCK": "true",
                    "SECRET_KEY": "$(head -c 32 /dev/urandom | base64)",
                },
            },
        ),
    ],
)
