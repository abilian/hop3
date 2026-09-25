# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A config the proxy refuses must not stay in the include directory.

`nginx -t` validates the whole tree, so the candidate has to be written before
it can be judged — and it used to stay there when the answer was no. From then
on every `nginx -t` failed: the next app's deploy, and every certificate
renewal, both aborted on a file belonging to an app neither of them named.

A failed *reload* deliberately does NOT roll back. "Rejected" is unambiguous;
"the reload did not take" is not — nginx forks its workers asynchronously, so
a reload reported as failed may have been slow on a loaded host and already
applied. Rolling back there would leave the file disagreeing with what nginx
is serving, and the next reload would silently revert this app's routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from hop3.core.protocols import BaseProxy
from hop3.lib.path import REJECTED_SUFFIX

GOOD = "server { listen 80; }\n"
NEW_GOOD = "server { listen 80; server_name new; }\n"
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

    def refuse_unsupported(self) -> None: ...
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
    def test_a_first_deploy_leaves_nothing_behind(self, conf) -> None:
        with pytest.raises(RefusedError):
            make_proxy(conf, BAD, "check").setup()
        assert not conf.exists(), "the next `nginx -t` would read this file"

    def test_a_redeploy_keeps_the_config_that_is_running(self, conf) -> None:
        conf.write_text(GOOD)
        with pytest.raises(RefusedError):
            make_proxy(conf, BAD, "check").setup()
        assert conf.read_text() == GOOD

    def test_an_accepted_config_is_installed(self, conf) -> None:
        conf.write_text("server { listen 80; server_name old; }\n")
        make_proxy(conf, GOOD).setup()
        assert conf.read_text() == GOOD


class TestAFailedReloadKeepsTheValidatedConfig:
    """
    A reload reported as failed may have been slow rather than refused: the
    e2e suite hit exactly that, nginx accepting a reload and logging no error
    but forking no worker inside rootd's 15s budget on a loaded host. The
    config was validated, so leaving it costs nothing — it passes `nginx -t`
    — and the next reload applies it. Rolling it back would desync the file
    from what nginx is serving.
    """

    def test_the_new_config_stays_on_disk(self, conf) -> None:
        conf.write_text(GOOD)
        with pytest.raises(RefusedError):
            make_proxy(conf, NEW_GOOD, "reload").setup()
        assert conf.read_text() == NEW_GOOD

    def test_nothing_is_parked_as_rejected(self, conf, rejected) -> None:
        """It was not rejected; calling it so would misname the failure."""
        with pytest.raises(RefusedError):
            make_proxy(conf, NEW_GOOD, "reload").setup()
        assert not rejected.exists()

    def test_the_deploy_still_fails(self, conf) -> None:
        """Routes are not live, so the deploy must not report success."""
        with pytest.raises(RefusedError):
            make_proxy(conf, NEW_GOOD, "reload").setup()


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
