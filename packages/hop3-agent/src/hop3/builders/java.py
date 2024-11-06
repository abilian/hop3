# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from pathlib import Path

from hop3.system.constants import APP_ROOT, ENV_ROOT
from hop3.util import log, prepend_to_path, shell
from hop3.util.settings import parse_settings


def build_java_gradle(app_name: str) -> None:
    """Deploy a Java application using Gradle."""
    java_path = ENV_ROOT / app_name
    build_path = APP_ROOT / app_name / "build"
    env_file = APP_ROOT / app_name / "ENV"

    env = {
        "VIRTUAL_ENV": java_path,
        "PATH": prepend_to_path([
            java_path / "bin",
            # FIXME: probably bad
            Path(app_name) / ".bin",
        ]),
    }

    if os.path.exists(env_file):
        env.update(parse_settings(env_file, env))

    if not os.path.exists(java_path):
        java_path.mkdir(parents=True)

    if os.path.exists(build_path):
        log("Removing previous builds", level=5)
        shell("gradle clean", cwd=APP_ROOT / app_name, env=env)

    log("Building Java Application with Gradle", level=5)
    shell("gradle build", cwd=APP_ROOT / app_name, env=env)


def build_java_maven(app_name: str) -> None:
    """Deploy a Java application using Maven."""
    # TODO: Use jenv to isolate Java Application environments

    java_path = ENV_ROOT / app_name
    target_path = APP_ROOT / app_name / "target"
    env_file = APP_ROOT / app_name / "ENV"

    env = {
        "VIRTUAL_ENV": java_path,
        "PATH": prepend_to_path([
            java_path / "bin",
            # FIXME: probably bad
            Path(app_name) / ".bin",
        ]),
    }

    if env_file.exists():
        env.update(parse_settings(env_file, env))

    if not os.path.exists(java_path):
        java_path.mkdir(parents=True)

    if target_path.exists():
        log("Removing previous builds", level=5)
        shell("mvn clean", cwd=APP_ROOT / app_name, env=env)

    log("Building Java Application with Maven", level=5)
    shell("mvn package", cwd=APP_ROOT / app_name, env=env)
