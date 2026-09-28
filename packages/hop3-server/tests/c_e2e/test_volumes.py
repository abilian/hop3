# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Declaring a volume for data an app already keeps in `src/` must not lose it.

Every deploy replaces `src/`. Until a recipe declares a volume, whatever its
app writes there lives in the tree, and the deploy that declares the volume is
the one that replaces that tree. The platform sets the old tree aside and seeds
the new, empty volume from it (`hop3.deployers.volumes`), so that deploy moves
the data instead of deleting it. The unit tests pin the mechanism; this runs
the real deploy path end to end, upload and all.
"""

from __future__ import annotations

import pytest
from hop3_testing.apps import DeploymentSession
from hop3_testing.apps.catalog import AppSource

from .conftest import create_flask_app

VOLUME_TOML = '[[volumes]]\nname = "data"\ntarget = "data"\n'


@pytest.mark.e2e
def test_a_volume_declared_later_keeps_what_the_app_wrote(
    deployment_target, tmp_path
) -> None:
    app_dir = create_flask_app(tmp_path, "vol-app", "Hello volumes")
    with DeploymentSession(
        AppSource(name="vol-app", path=app_dir), deployment_target
    ) as session:
        session.deploy()
        root = f"/home/hop3/apps/{session.app_name}"

        # What the running app wrote into its own tree, as its own user.
        code, _, err = deployment_target.exec_run([
            "su",
            "hop3",
            "-s",
            "/bin/sh",
            "-c",
            f"mkdir -p {root}/src/data && echo precious > {root}/src/data/app.db",
        ])
        assert code == 0, err

        # The next version of the recipe declares the volume.
        (session.temp_dir / "hop3.toml").write_text(VOLUME_TOML)
        session.deploy()

        code, out, err = deployment_target.exec_run([
            "cat",
            f"{root}/volumes/data/app.db",
        ])
        assert (code, out.strip()) == (0, "precious"), err
        code, out, _ = deployment_target.exec_run(["readlink", f"{root}/src/data"])
        assert out.strip() == "../volumes/data"
        # The tree kept for the seeding is gone once the volume is realized.
        code, _, _ = deployment_target.exec_run(["test", "-e", f"{root}/src.previous"])
        assert code != 0

        # And the deploy after that keeps it: the volume is now the only copy.
        session.deploy()
        code, out, _ = deployment_target.exec_run(["cat", f"{root}/src/data/app.db"])
        assert out.strip() == "precious"
