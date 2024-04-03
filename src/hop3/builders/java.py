from __future__ import annotations

import os
from pathlib import Path

from hop3.system.constants import APP_ROOT, ENV_ROOT
from hop3.util import shell
from hop3.util.console import log
from hop3.util.settings import parse_settings


def build_java_gradle(app_name: str) -> None:
    """Deploy a Java application using Gradle"""

    java_path = os.path.join(ENV_ROOT, app_name)
    build_path = os.path.join(APP_ROOT, app_name, "build")
    env_file = os.path.join(APP_ROOT, app_name, "ENV")

    env = {
        "VIRTUAL_ENV": java_path,
        "PATH": ":".join(
            [
                os.path.join(java_path, "bin"),
                os.path.join(app_name, ".bin"),
                os.environ["PATH"],
            ]
        ),
    }

    if os.path.exists(env_file):
        env.update(parse_settings(env_file, env))

    if not os.path.exists(java_path):
        os.makedirs(java_path)

    if os.path.exists(build_path):
        log("Removing previous builds", level=5)
        shell("gradle clean", cwd=Path(APP_ROOT, app_name), env=env)

    log("Building Java Application with Gradle", level=5)
    shell("gradle build", cwd=Path(APP_ROOT, app_name), env=env)


def build_java_maven(app_name: str) -> None:
    """Deploy a Java application using Maven"""
    # TODO: Use jenv to isolate Java Application environments

    java_path = os.path.join(ENV_ROOT, app_name)
    target_path = os.path.join(APP_ROOT, app_name, "target")
    env_file = os.path.join(APP_ROOT, app_name, "ENV")

    env = {
        "VIRTUAL_ENV": java_path,
        "PATH": ":".join(
            [
                os.path.join(java_path, "bin"),
                os.path.join(app_name, ".bin"),
                os.environ["PATH"],
            ]
        ),
    }

    if os.path.exists(env_file):
        env.update(parse_settings(env_file, env))

    if not os.path.exists(java_path):
        os.makedirs(java_path)

    if os.path.exists(target_path):
        log("Removing previous builds", level=5)
        shell("mvn clean", cwd=Path(APP_ROOT, app_name), env=env)

    log("Building Java Application with Maven", level=5)
    shell("mvn package", cwd=Path(APP_ROOT, app_name), env=env)
