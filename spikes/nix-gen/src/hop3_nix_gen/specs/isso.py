"""Isso: Python commenting system, installed via pip into a venv."""

from hop3_nix_gen.spec import AppSpec, ConfigFile, Source

_CONFIG_INI = """[general]
dbpath = data/comments.db
host = http://localhost:${PORT:-8080}

[server]
listen = http://${BIND_ADDRESS:-0.0.0.0}:${PORT:-8080}
"""

SPEC = AppSpec(
    pname="isso",
    version="0.13.1",
    description="A lightweight commenting system, Disqus alternative",
    template="python-venv",
    runtime_package="python3",
    pip_packages=["isso", "gunicorn"],
    # python-venv skips source fetch, but AppSpec requires a source field.
    # Use a sentinel URL that won't be evaluated.
    source=Source(
        url="file:///dev/null",
        sha256="",
    ),
    exec_target="isso",
    exec_args=["-c", "isso-runtime.cfg"],
    pre_exec_commands=[
        "mkdir -p data",
    ],
    config_files=[
        ConfigFile(
            path="isso-runtime.cfg",
            format="raw",
            raw_content=_CONFIG_INI,
        ),
    ],
    extra_paths=["$out/venv/bin"],
)
