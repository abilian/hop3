# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The supervisor programs the scripts manage are the ones the configs define.

The uWSGI emperor's program was renamed `uwsgi` -> `uwsgi-hop3`, its systemd
unit's name, in the configs; the restore script and the post-install check
kept asking supervisor for `uwsgi`. Supervisor answers "no such process", so
a restore on a Docker install stopped at "uwsgi did not start" after it had
already replaced the database and the apps tree.
"""

from __future__ import annotations

import re
from pathlib import Path

from hop3_installer.deployer.backends.docker import SUPERVISOR_CONFIG
from hop3_installer.deployer.restore import SERVER_SCRIPT
from hop3_installer.server_installer.verify import SUPERVISOR_SERVICES

_PROGRAM = re.compile(r"^\[program:([\w-]+)\]", re.MULTILINE)
_INSTALLER_IMAGE_CONFIG = Path(__file__).parents[2] / "docker" / "supervisor-hop3.conf"


def _programs(config: str) -> set[str]:
    return set(_PROGRAM.findall(config))


def _restore_requires() -> set[str]:
    """
    The services the restore fails without: the emperor, and each one
    started unconditionally (Redis is started only where it is installed).
    """
    script = SERVER_SCRIPT.read_text()
    uwsgi = re.search(r"^UWSGI_SVC=(\S+)$", script, re.MULTILINE)
    assert uwsgi, "the restore script no longer names the emperor's service"
    started = re.findall(r"^svc_start ([\w-]+) \|\| fail", script, re.MULTILINE)
    assert started, "the restore script no longer starts hop3-server"
    return {uwsgi[1], *started}


def test_restore_starts_programs_the_docker_backend_defines():
    assert _restore_requires() <= _programs(SUPERVISOR_CONFIG)


def test_restore_starts_programs_the_installer_image_defines():
    programs = _programs(_INSTALLER_IMAGE_CONFIG.read_text())
    assert _restore_requires() <= programs


def test_post_install_check_asks_for_defined_programs():
    for config in (SUPERVISOR_CONFIG, _INSTALLER_IMAGE_CONFIG.read_text()):
        assert set(SUPERVISOR_SERVICES) <= _programs(config)
