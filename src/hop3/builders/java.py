# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import os
from pathlib import Path

from hop3.system.constants import APP_ROOT, ENV_ROOT
from hop3.util import shell
from hop3.util.console import log
from hop3.util.settings import parse_settings

#         if Path(app_path, "pom.xml").exists() and check_binaries(["java", "mvn"]):
#             log("Java Maven app detected.", level=5, fg="green")
#             build_java_maven(app_name)
#             builder_detected = True
#
#         if Path(app_path, "build.gradle").exists() and check_binaries(
#             ["java", "gradle"]
#         ):
#             log("Java Gradle app detected.", level=5, fg="green")
#             build_java_gradle(app_name)
#             builder_detected = True


def build_java_gradle(app_name: str) -> None:
    """Deploy a Java application using Gradle."""
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
            ],
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
    """Deploy a Java application using Maven."""
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
            ],
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
