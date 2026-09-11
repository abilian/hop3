# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A config the proxy refuses must not stay in the include directory.

`nginx -t` validates the whole tree, so the candidate has to be written before
it can be judged — and it used to stay there when the answer was no. From then
on every `nginx -t` failed: the next app's deploy, and every certificate
renewal, both aborted on a file belonging to an app neither of them named.

A failed *reload* rolls back for the same reason, and because the previous
content is what the running proxy still has loaded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from hop3.core.protocols import BaseProxy
from hop3.lib.path import REJECTED_SUFFIX

GOOD = "server { listen 80; }\n"
BAD = "server { listen 80;\n"


class RefusedError(Exception):
    """What a proxy plugin raises when its own checker says no."""


@dataclass(frozen=True)
class StubProxy(BaseProxy):
    """A proxy whose only real behaviour is writing and judging its config."""

    path: Path = field(default_factory=Path)
    content: str = GOOD
    fails_at: str = ""

    def get_proxy_name(self) -> str:
        return "stub"

    @property
    def conf_path(self) -> Path:
        return self.path

    def setup_backend(self) -> None: ...
    def setup_certificates(self) -> None: ...
    def setup_cache(self) -> None: ...
    def setup_static(self) -> None: ...
    def extra_setup(self) -> None: ...

    def generate_config(self) -> None:
        self.conf_path.write_text(self.content)

    def check_config(self) -> None:
        if self.fails_at == "check":
            raise RefusedError

    def reload_proxy(self) -> None:
        if self.fails_at == "reload":
            raise RefusedError


def make_proxy(path: Path, content: str, fails_at: str = "") -> StubProxy:
    return StubProxy(
        app=None, env={}, workers={}, path=path, content=content, fails_at=fails_at
    )


@pytest.fixture
def conf(tmp_path) -> Path:
    return tmp_path / "myapp.conf"


@pytest.fixture
def rejected(conf) -> Path:
    return conf.with_name(conf.name + REJECTED_SUFFIX)


class TestTheIncludeDirectoryOnlyHoldsAcceptedConfigs:
    @pytest.mark.parametrize("fails_at", ["check", "reload"])
    def test_a_first_deploy_leaves_nothing_behind(self, conf, fails_at) -> None:
        with pytest.raises(RefusedError):
            make_proxy(conf, BAD, fails_at).setup()
        assert not conf.exists(), "the next `nginx -t` would read this file"

    @pytest.mark.parametrize("fails_at", ["check", "reload"])
    def test_a_redeploy_keeps_the_config_that_is_running(self, conf, fails_at) -> None:
        conf.write_text(GOOD)
        with pytest.raises(RefusedError):
            make_proxy(conf, BAD, fails_at).setup()
        assert conf.read_text() == GOOD

    def test_an_accepted_config_is_installed(self, conf) -> None:
        conf.write_text("server { listen 80; server_name old; }\n")
        make_proxy(conf, GOOD).setup()
        assert conf.read_text() == GOOD


class TestTheRejectedConfigIsKeptForInspection:
    """The diagnosis tells the operator to read it, so it has to be there."""

    def test_it_is_parked_beside_the_live_one(self, conf, rejected) -> None:
        with pytest.raises(RefusedError):
            make_proxy(conf, BAD, "check").setup()
        assert rejected.read_text() == BAD

    def test_its_name_is_outside_the_conf_glob(self, rejected) -> None:
        assert not rejected.match("*.conf"), "nginx includes /home/hop3/nginx/*.conf"

    def test_a_later_success_clears_it(self, conf, rejected) -> None:
        with pytest.raises(RefusedError):
            make_proxy(conf, BAD, "check").setup()
        make_proxy(conf, GOOD).setup()
        assert not rejected.exists(), "it describes a failure that is now fixed"
