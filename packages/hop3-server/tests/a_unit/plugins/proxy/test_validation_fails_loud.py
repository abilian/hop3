# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A config that was never validated must not be deployed.

Both plugins used to warn and carry on: caddy when `caddy validate` could not
be run at all (binary absent, check timed out), traefik when anything but a
YAML error came out of the parse. A deploy then reported success having
checked nothing — the failure shape the fail-loud rule exists to prevent, and
the one nginx already avoids by aborting with a `Diagnosis`.

Traefik also carried an `except ImportError: "PyYAML not installed, skipping
config validation"`. `import yaml` is at module top and pyyaml is a hard
dependency, so the module could not have loaded to reach it.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from hop3.core.env import Env
from hop3.lib import Abort
from hop3.orm import App
from hop3.plugins.proxy.caddy import CaddyVirtualHost, _setup as caddy_setup
from hop3.plugins.proxy.traefik import TraefikVirtualHost

ENV = {
    "APP": "testapp",
    "PORT": "8000",
    "HOST_NAME": "testapp.com",
    "BIND_ADDRESS": "127.0.0.1",
}


@pytest.fixture
def conf_path(tmp_path, monkeypatch):
    """Point both plugins' `conf_path` at a writable file."""
    path = tmp_path / "testapp.conf"
    for cls in (CaddyVirtualHost, TraefikVirtualHost):
        monkeypatch.setattr(cls, "conf_path", property(lambda self: path))
    return path


def caddy_host() -> CaddyVirtualHost:
    return CaddyVirtualHost(App(name="testapp"), Env(dict(ENV)), {})


def traefik_host() -> TraefikVirtualHost:
    return TraefikVirtualHost(App(name="testapp"), Env(dict(ENV)), {})


def stub_run(monkeypatch, outcome):
    """Replace `caddy validate` with a stub that raises or returns.

    The plugin's whole `subprocess` reference is swapped, not the real
    module's `run`: that object is shared, and patching it also caught
    `command_output("caddy version")` in `__post_init__`.
    """

    def run(argv, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(
        caddy_setup,
        "subprocess",
        SimpleNamespace(
            run=run,
            CalledProcessError=subprocess.CalledProcessError,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )


class TestCaddyRefusesToPassAnUncheckedConfig:
    def test_a_rejected_config_aborts_with_the_validator_output(
        self, conf_path, monkeypatch
    ) -> None:
        stub_run(
            monkeypatch,
            subprocess.CalledProcessError(
                1, "caddy", stderr=b"line 3: unrecognized directive: reverse_proxyy"
            ),
        )
        with pytest.raises(Abort) as excinfo:
            caddy_host().check_config()
        assert "unrecognized directive" in str(excinfo.value)

    def test_a_missing_binary_aborts_instead_of_warning(
        self, conf_path, monkeypatch
    ) -> None:
        """It used to log a warning, and the deploy went out unvalidated."""
        stub_run(monkeypatch, FileNotFoundError("caddy"))
        with pytest.raises(Abort) as excinfo:
            caddy_host().check_config()
        assert "not on PATH" in str(excinfo.value)

    def test_a_timeout_aborts_instead_of_warning(self, conf_path, monkeypatch) -> None:
        stub_run(monkeypatch, subprocess.TimeoutExpired("caddy", 5))
        with pytest.raises(Abort):
            caddy_host().check_config()

    def test_the_diagnosis_names_the_rejected_copy(
        self, conf_path, monkeypatch
    ) -> None:
        """`setup` rolls the file back, so the live path would not hold it."""
        stub_run(monkeypatch, FileNotFoundError("caddy"))
        with pytest.raises(Abort) as excinfo:
            caddy_host().check_config()
        assert str(caddy_host().rejected_conf_path) in str(excinfo.value)

    def test_a_valid_config_passes(self, conf_path, monkeypatch) -> None:
        stub_run(monkeypatch, subprocess.CompletedProcess(["caddy"], 0))
        caddy_host().check_config()


class TestTraefikRefusesToPassAnUncheckedConfig:
    def test_unparseable_yaml_aborts(self, conf_path) -> None:
        conf_path.write_text("http:\n  routers:\n   - [unclosed\n")
        with pytest.raises(Abort) as excinfo:
            traefik_host().check_config()
        assert "not valid YAML" in str(excinfo.value)

    def test_the_diagnosis_names_the_rejected_copy(self, conf_path) -> None:
        conf_path.write_text("http:\n  routers:\n   - [unclosed\n")
        with pytest.raises(Abort) as excinfo:
            traefik_host().check_config()
        assert str(traefik_host().rejected_conf_path) in str(excinfo.value)

    def test_valid_yaml_passes(self, conf_path) -> None:
        conf_path.write_text("http:\n  routers: {}\n")
        traefik_host().check_config()
