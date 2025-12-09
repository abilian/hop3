#!/usr/bin/env python3
"""Taiga start script for Hop3."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
PKG_DIR = Path(os.environ.get("HOP3_PKG_DIR", "/app/pkg"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost:8000")
HOP3_APP_DOMAIN = os.environ.get("HOP3_APP_DOMAIN", "localhost")

# LDAP configuration
LDAP_HOST = os.environ.get("LDAP_HOST", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def main() -> int:
    # Create directories
    (DATA_DIR / "media").mkdir(parents=True, exist_ok=True)
    for subdir in [
        "nginx",
        "client_body",
        "proxy_temp",
        "fastcgi_temp",
        "scgi_temp",
        "uwsgi_temp",
    ]:
        Path(f"/run/{subdir}").mkdir(parents=True, exist_ok=True)

    # Setup symlinks
    media_link = CODE_DIR / "taiga-back" / "media"
    if media_link.is_symlink() or media_link.exists():
        media_link.unlink()
    media_link.symlink_to(DATA_DIR / "media")

    nginx_log = Path("/var/log/nginx")
    if nginx_log.is_symlink() or nginx_log.exists():
        if nginx_log.is_symlink():
            nginx_log.unlink()
        else:
            shutil.rmtree(nginx_log)
    nginx_log.symlink_to("/run/nginx")

    conf_json_link = CODE_DIR / "taiga-front-dist" / "dist" / "conf.json"
    if conf_json_link.is_symlink() or conf_json_link.exists():
        conf_json_link.unlink()
    conf_json_link.symlink_to(DATA_DIR / "conf.json")

    # Copy local.py config
    shutil.copy(
        PKG_DIR / "templates" / "local.py",
        CODE_DIR / "taiga-back" / "settings" / "config.py",
    )

    # Create customlocal.py if not exists
    customlocal = DATA_DIR / "customlocal.py"
    if not customlocal.exists():
        customlocal.write_text("# Place custom local.py settings in this file\n")

    # Create conf.json if not exists
    conf_json = DATA_DIR / "conf.json"
    if not conf_json.exists():
        conf_json.write_text("{}")

    # Merge conf.json based on LDAP
    if LDAP_HOST:
        print("=> Update conf.json with LDAP")
        run(
            [
                "node",
                str(PKG_DIR / "conf" / "json-merge.js"),
                str(conf_json),
                str(PKG_DIR / "templates" / "conf_ldap.json"),
            ]
        )
    else:
        print("=> Update conf.json")
        run(
            [
                "node",
                str(PKG_DIR / "conf" / "json-merge.js"),
                str(conf_json),
                str(PKG_DIR / "templates" / "conf.json"),
            ]
        )

    # Update API URL in conf.json
    run(
        [
            str(CODE_DIR / "node_modules" / ".bin" / "json"),
            "-I",
            "-f",
            str(conf_json),
            "-e",
            f"this.api = '{HOP3_APP_ORIGIN}/api/v1/'",
        ]
    )

    print("=> Update nginx.conf")
    nginx_template = (PKG_DIR / "conf" / "nginx.conf").read_text()
    nginx_config = nginx_template.replace("##APP_DOMAIN##", HOP3_APP_DOMAIN)
    Path("/run/nginx.conf").write_text(nginx_config)

    print("=> Setup taiga virtual env")
    # We'll use the virtual env by setting PATH and other env vars
    venv_bin = CODE_DIR / "venv" / "bin"
    os.environ["PATH"] = f"{venv_bin}:{os.environ.get('PATH', '')}"
    os.environ["VIRTUAL_ENV"] = str(CODE_DIR / "venv")

    os.environ["DJANGO_SETTINGS_MODULE"] = "settings.config"

    os.chdir(CODE_DIR / "taiga-back")

    media_user = DATA_DIR / "media" / "user"
    if not media_user.exists():
        print("=> New installation create initial project templates")
        print("=> Run migration scripts")
        media_user.mkdir(parents=True, exist_ok=True)

        run(["python3.11", "manage.py", "migrate", "--noinput"])
        run(["python3.11", "manage.py", "loaddata", "initial_user"])
        run(["python3.11", "manage.py", "loaddata", "initial_project_templates"])
    else:
        print("=> Run migration scripts")
        run(["python3.11", "manage.py", "migrate", "--noinput"])

    print("=> Make hop3 user own /run")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", "/run"])
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR)])

    print("=> Start nginx")
    subprocess.Popen(["nginx", "-c", "/run/nginx.conf"])

    print("=> Start taiga-back")
    os.environ["HOME"] = str(CODE_DIR)

    # Calculate worker count based on available memory
    try:
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes") as f:
            memory_limit = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        memory_limit = 314572800  # Default ~300MB

    worker_count = memory_limit // 1024 // 1024 // 150  # 1 worker per 150MB
    worker_count = min(max(worker_count, 1), 8)  # Clamp between 1 and 8

    print(f"Starting gunicorn with {worker_count} workers")
    os.execvp(
        "su",
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"source {CODE_DIR}/venv/bin/activate && gunicorn -w {worker_count} -t 60 --pythonpath=. -b 127.0.0.1:8001 taiga.wsgi",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
