# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Regression: destroying a docker-compose app must remove its image.

Without `--rmi all` (and the force-rmi safety net), every docker-variant
deploy leaks a 0.5-1.5 GB `hop3/<app>:latest` image — and since the app
name is timestamped, the tag is unique each run and never overwritten, so
the disk fills fast. See App._destroy_docker_compose.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hop3.orm import App


def _record_subprocess():
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    return calls, fake_run


def test_destroy_docker_compose_removes_the_app_image():
    app = App(
        name="bugsink-1780956657",
        runtime="docker-compose",
        image_tag="hop3/bugsink-1780956657:latest",
    )
    calls, fake_run = _record_subprocess()

    with patch("hop3.orm.app.subprocess.run", side_effect=fake_run):
        app._destroy_docker_compose()

    # The compose-down must request image removal...
    down = next(c for c in calls if "down" in c)
    assert "--rmi" in down
    assert down[down.index("--rmi") + 1] == "all"

    # ...and the per-app image is force-removed as a safety net.
    assert any(
        c[:2] == ["docker", "rmi"] and "hop3/bugsink-1780956657:latest" in c
        for c in calls
    ), f"expected a 'docker rmi' of the app image, got: {calls}"


def test_force_cleanup_docker_image_targets_only_the_app_image():
    app = App(name="myapp", runtime="docker-compose", image_tag="hop3/myapp:latest")
    calls, fake_run = _record_subprocess()

    with patch("hop3.orm.app.subprocess.run", side_effect=fake_run):
        app._force_cleanup_docker_image()

    assert calls == [["docker", "rmi", "-f", "hop3/myapp:latest"]]
