"""Miniflux: prebuilt Go binary, PostgreSQL backend."""

from hop3_nix_gen.spec import AppSpec, ConditionalEnvVar, Source

SPEC = AppSpec(
    pname="miniflux",
    version="2.1.1",
    description="Minimalist and opinionated RSS reader",
    template="prebuilt-binary",
    binary_name="miniflux",
    source=Source(
        url="https://github.com/miniflux/v2/releases/download/${version}/miniflux-linux-amd64",
        sha256="ydbOKn/voD05Hvl1wAU2GUcCccHimmB/2b0q+4RrKcU=",
        executable=True,
    ),
    env_exports={
        "LISTEN_ADDR": "0.0.0.0:${PORT:-8080}",
        "RUN_MIGRATIONS": "1",
        "CREATE_ADMIN": "1",
        "ADMIN_USERNAME": "${ADMIN_USERNAME:-admin}",
        "ADMIN_PASSWORD": "${ADMIN_PASSWORD:-changeme}",
    },
    conditional_env_exports=[
        ConditionalEnvVar(
            name="DATABASE_URL",
            condition_var="DATABASE_URL",
            value="postgres://${PGUSER:-miniflux}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-miniflux}?sslmode=disable",
        ),
    ],
    runtime_env={
        "RUN_MIGRATIONS": "1",
        "CREATE_ADMIN": "1",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "changeme",
    },
)
