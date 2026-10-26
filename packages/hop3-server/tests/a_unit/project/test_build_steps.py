# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
[build].build runs exactly once, or the deploy refuses it.

The toolchain runs it in place of its own install (the conformance test over
every toolchain pins that). The deployer used to run it a second time after the
build, so every declared build ran twice. Only the local builder runs a
toolchain, so under Docker or Nix the command would never run: that is refused,
since a declared step that does not run is a lie.
"""

from __future__ import annotations

import pytest

from hop3.deployers.deployer import _reject_build_off_local
from hop3.lib import Abort


@pytest.mark.parametrize("builder", ["docker", "nix"])
def test_a_build_command_off_the_local_builder_is_refused(builder) -> None:
    with pytest.raises(Abort, match="make miniflux"):
        _reject_build_off_local(builder, ["make miniflux"])


def test_the_local_builder_runs_it() -> None:
    _reject_build_off_local("local", ["npm ci", "npm run build"])


@pytest.mark.parametrize("builder", ["local", "docker", "nix"])
def test_no_build_command_is_fine_anywhere(builder) -> None:
    _reject_build_off_local(builder, [])
