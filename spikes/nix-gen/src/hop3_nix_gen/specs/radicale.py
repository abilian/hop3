"""Radicale: CalDAV/CardDAV server, wrapped from the nixpkgs package."""

from hop3_nix_gen.spec import AppSpec, ConfigFile, Source

_CONFIG_INI = """[server]
hosts = 0.0.0.0:${PORT}

[auth]
type = ${RADICALE_AUTH_TYPE:-none}

[storage]
filesystem_folder = collections
"""

SPEC = AppSpec(
    pname="radicale",
    version="",  # Inherited from nixpkgs package version
    description="A simple CalDAV and CardDAV server",
    template="nixpkgs-wrapper",
    nixpkgs_package="radicale",
    # nixpkgs-wrapper doesn't fetch source, but AppSpec requires Source.
    source=Source(url="file:///dev/null", sha256=""),
    exec_target="radicale",
    exec_args=["--config", "config", '"$@"'],
    local_vars={
        "PORT": "${PORT:-8080}",
    },
    pre_exec_commands=[
        "mkdir -p collections",
    ],
    config_files=[
        ConfigFile(
            path="config",
            format="raw",
            raw_content=_CONFIG_INI,
            create_if_missing=True,
        ),
    ],
    runtime_env={
        "RADICALE_AUTH_TYPE": "none",
    },
    extra_paths=["${radicale}/bin"],
)
