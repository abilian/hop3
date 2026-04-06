"""Wiki.js: Node.js prebuilt release, PostgreSQL backend."""

from hop3_nix_gen.spec import AppSpec, ConfigFile, Source

_SYMLINK_LOOP = """# Symlink Wiki.js assets from the read-only Nix store to the writable cwd
for item in server node_modules assets package.json; do
  if [ -e APPDIR/$item ] && [ ! -e $item ]; then
    ln -sf APPDIR/$item $item
  fi
done"""

_CONFIG_YAML = """port: ${PORT}
bindIP: 0.0.0.0

db:
  type: postgres
  host: ${DB_HOST}
  port: ${DB_PORT}
  user: ${DB_USER}
  pass: ${DB_PASS}
  db: ${DB_NAME}
  ssl: false

logLevel: info

offline: false
ha: false

dataPath: ./data
"""

SPEC = AppSpec(
    pname="wiki-js",
    version="2.5.303",
    description="Modern and powerful wiki platform",
    template="node-prebuilt",
    runtime_package="nodejs_22",
    source=Source(
        url="https://github.com/Requarks/wiki/releases/download/v${version}/wiki-js.tar.gz",
        sha256="Jpv4D+ldGPvJz+8cwNhrmC+Ii5dG0UOTC5JIWPwUzvk=",
        archive="tar-gz",
    ),
    unpack_without_top_level=True,
    exec_target="server/index.js",
    local_vars={
        "PORT": "${PORT:-8080}",
        "DB_HOST": "${PGHOST:-localhost}",
        "DB_PORT": "${PGPORT:-5432}",
        "DB_NAME": "${PGDATABASE:-wikijs}",
        "DB_USER": "${PGUSER:-wikijs}",
        "DB_PASS": "${PGPASSWORD:-}",
    },
    env_exports={
        "NODE_ENV": "production",
    },
    pre_exec_commands=[
        "mkdir -p data",
        _SYMLINK_LOOP,
    ],
    config_files=[
        ConfigFile(
            path="config.yml",
            format="raw",
            raw_content=_CONFIG_YAML,
        ),
    ],
    runtime_env={
        "NODE_ENV": "production",
    },
    extra_paths=["${nodejs}/bin"],
)
