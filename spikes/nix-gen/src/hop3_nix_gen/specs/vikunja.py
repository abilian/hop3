"""Vikunja: zip archive, YAML config, PostgreSQL backend."""

from hop3_nix_gen.spec import AppSpec, ConfigFile, FileMapping, Source

_CONFIG_YAML = """service:
  interface: ":${PORT}"
  frontendurl: "${VIKUNJA_FRONTEND_URL:-http://localhost:${PORT}/}"

database:
  type: postgres
  host: ${PGHOST:-localhost}
  port: ${PGPORT:-5432}
  database: ${PGDATABASE:-vikunja}
  user: ${PGUSER:-vikunja}
  password: ${PGPASSWORD:-}

files:
  basepath: ./files
"""

SPEC = AppSpec(
    pname="vikunja",
    version="0.24.6",
    description="Open source task and project management",
    template="prebuilt-archive",
    source=Source(
        url="https://dl.vikunja.io/vikunja/${version}/vikunja-v${version}-linux-amd64-full.zip",
        sha256="AAfg+56IAhs5DYmK2IpE2JgdUv7lfsGeBYZwOvso8Bo=",
        unpack=True,
        unpacker="unzip",
    ),
    source_root=".",
    file_mappings=[
        # The zip contains a binary named vikunja-v0.24.6-linux-amd64
        FileMapping(
            source="vikunja-v${version}-linux-amd64",
            destination="bin/vikunja",
            recursive=False,
            executable=True,
        ),
    ],
    exec_target="vikunja",
    local_vars={
        "PORT": "${PORT:-8080}",
    },
    pre_exec_commands=[
        "mkdir -p files",
    ],
    config_files=[
        ConfigFile(
            path="config.yml",
            format="raw",
            raw_content=_CONFIG_YAML,
            create_if_missing=True,
        ),
    ],
    runtime_env={
        "VIKUNJA_FRONTEND_URL": "http://localhost:8080/",
    },
)
