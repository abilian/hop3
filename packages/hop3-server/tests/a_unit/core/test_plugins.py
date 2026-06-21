# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the plugin manager helper logic in ``hop3.core.plugins``.

These tests exercise the *selection* logic of the helper functions
(``get_builder``, ``get_deployer``, ``get_addon``, ...) and the pure
deployment-hint builders. The real ``PluginManager`` singleton is replaced
with an in-memory stub so the tests are hermetic: no plugin discovery, no
Docker, no host mutation. The singleton is restored automatically because we
patch it via ``monkeypatch``.
"""

from __future__ import annotations

import inspect
import types
from pathlib import Path

import pytest

import hop3.plugins.redis as redis_pkg
import hop3.plugins.redis.plugin  # noqa: F401 — binds redis_pkg.plugin attribute
from hop3.core import plugins
from hop3.core.plugins import (
    _build_deployment_hints,
    _hints_for_docker_image,
    _hints_for_static,
    _hints_for_unknown_artifact,
    _hints_for_virtualenv,
    _iter_module_names,
    get_addon,
    get_builder,
    get_deployer,
    get_deployer_by_name,
    get_os_strategy,
    get_plugin_manager,
    get_proxy_strategy,
    list_supported_os,
)
from hop3.core.protocols import BuildArtifact, DeploymentContext

# --- Test doubles ---------------------------------------------------------


class StubHook:
    """A pluggy-like ``pm.hook`` whose hook calls return preset lists-of-lists.

    Each pluggy hook returns one list per registered plugin; the helper
    functions flatten that into a single list. We mirror that shape: a hook
    name maps to a list of sublists.
    """

    def __init__(self, **hook_results: list[list]) -> None:
        self._results = hook_results

    def __getattr__(self, name: str):
        results = self._results.get(name, [])

        def _call() -> list[list]:
            return results

        return _call


class StubPluginManager:
    """Minimal stand-in for ``pluggy.PluginManager`` exposing ``.hook``."""

    def __init__(self, **hook_results: list[list]) -> None:
        self.hook = StubHook(**hook_results)


@pytest.fixture
def install_pm(monkeypatch):
    """Install a stub PluginManager as the module singleton.

    Returns a callable that takes hook results and wires them up. The original
    ``_plugin_manager`` is restored by monkeypatch teardown.
    """

    def _install(**hook_results: list[list]) -> StubPluginManager:
        pm = StubPluginManager(**hook_results)
        monkeypatch.setattr(plugins, "_plugin_manager", pm)
        return pm

    return _install


def make_context(tmp_path: Path, app_config: dict | None = None) -> DeploymentContext:
    """Build a real DeploymentContext rooted at an existing directory."""
    return DeploymentContext(
        app_name="myapp",
        source_path=tmp_path,
        app_config=app_config if app_config is not None else {},
    )


# --- get_builder ----------------------------------------------------------


class TestGetBuilder:
    def test_auto_detects_first_accepting_builder(self, install_pm, tmp_path):
        class Accepting:
            name = "accepting"

            def __init__(self, context) -> None:
                self.context = context

            def accept(self) -> bool:
                return True

        class Rejecting:
            name = "rejecting"

            def __init__(self, context) -> None:
                self.context = context

            def accept(self) -> bool:
                return False

        install_pm(get_builders=[[Rejecting, Accepting]])
        context = make_context(tmp_path)

        builder = get_builder(context)

        assert isinstance(builder, Accepting)
        assert builder.context is context

    def test_no_accepting_builder_raises_with_rejection_reasons(
        self, install_pm, tmp_path
    ):
        class Picky:
            name = "picky"

            def __init__(self, context) -> None:
                pass

            def accept(self) -> bool:
                return False

            rejection_reason = "no Procfile here"

        install_pm(get_builders=[[Picky]])
        context = make_context(tmp_path)

        with pytest.raises(RuntimeError) as exc_info:
            get_builder(context)

        message = str(exc_info.value)
        assert "Could not find a suitable builder" in message
        assert "Available builders: picky" in message
        assert "no Procfile here" in message

    def test_builder_constructor_error_is_recorded_in_message(
        self, install_pm, tmp_path
    ):
        class Exploding:
            name = "exploding"

            def __init__(self, context) -> None:
                msg = "boom"
                raise ValueError(msg)

            def accept(self) -> bool:
                return True

        install_pm(get_builders=[[Exploding]])
        context = make_context(tmp_path)

        with pytest.raises(RuntimeError) as exc_info:
            get_builder(context)

        assert "exploding: error - boom" in str(exc_info.value)

    def test_explicit_builder_selected_by_name(self, install_pm, tmp_path):
        accept_calls: list[str] = []

        class Local:
            name = "local"

            def __init__(self, context) -> None:
                self.context = context

            def accept(self) -> bool:
                accept_calls.append("local")
                return True

        class Docker:
            name = "docker"

            def __init__(self, context) -> None:
                self.context = context

            def accept(self) -> bool:
                accept_calls.append("docker")
                return True

        install_pm(get_builders=[[Local, Docker]])
        context = make_context(
            tmp_path, {"hop3_config": {"build": {"builder": "docker"}}}
        )

        builder = get_builder(context)

        assert isinstance(builder, Docker)
        # Explicit selection must not auto-detect (accept() never called).
        assert accept_calls == []

    def test_explicit_builder_not_found_raises(self, install_pm, tmp_path):
        class Local:
            name = "local"

            def __init__(self, context) -> None:
                pass

            def accept(self) -> bool:
                return True

        install_pm(get_builders=[[Local]])
        context = make_context(
            tmp_path, {"hop3_config": {"build": {"builder": "nonexistent"}}}
        )

        with pytest.raises(RuntimeError) as exc_info:
            get_builder(context)

        assert "Configured builder 'nonexistent' not found" in str(exc_info.value)

    def test_non_dict_hop3_config_falls_back_to_auto_detect(self, install_pm, tmp_path):
        class Accepting:
            name = "accepting"

            def __init__(self, context) -> None:
                pass

            def accept(self) -> bool:
                return True

        install_pm(get_builders=[[Accepting]])
        # hop3_config is not a dict -> build_config defaults to {} -> "auto".
        context = make_context(tmp_path, {"hop3_config": "not-a-dict"})

        builder = get_builder(context)

        assert isinstance(builder, Accepting)

    def test_non_dict_build_config_falls_back_to_auto_detect(
        self, install_pm, tmp_path
    ):
        class Accepting:
            name = "accepting"

            def __init__(self, context) -> None:
                pass

            def accept(self) -> bool:
                return True

        install_pm(get_builders=[[Accepting]])
        # build_config is present but not a dict -> builder name forced to "auto".
        context = make_context(tmp_path, {"hop3_config": {"build": "not-a-dict"}})

        builder = get_builder(context)

        assert isinstance(builder, Accepting)

    def test_hook_failure_is_reraised(self, install_pm, monkeypatch, tmp_path):
        pm = install_pm()

        def _raising_get_builders() -> list[list]:
            msg = "hook exploded"
            raise RuntimeError(msg)

        monkeypatch.setattr(pm.hook, "get_builders", _raising_get_builders)
        context = make_context(tmp_path)

        with pytest.raises(RuntimeError, match="hook exploded"):
            get_builder(context)


# --- get_deployer ---------------------------------------------------------


class TestGetDeployer:
    def test_returns_first_accepting_deployer(self, install_pm, tmp_path):
        class Uwsgi:
            name = "uwsgi"

            def __init__(self, context, artifact) -> None:
                self.context = context
                self.artifact = artifact

            def accept(self) -> bool:
                return True

        install_pm(get_deployers=[[Uwsgi]])
        context = make_context(tmp_path)
        artifact = BuildArtifact(kind="virtualenv", location="/tmp/venv")

        deployer = get_deployer(context, artifact)

        assert isinstance(deployer, Uwsgi)
        assert deployer.artifact is artifact

    def test_no_accepting_deployer_raises_with_hints(self, install_pm, tmp_path):
        class Uwsgi:
            name = "uwsgi"

            def __init__(self, context, artifact) -> None:
                pass

            def accept(self) -> bool:
                return False

        install_pm(get_deployers=[[Uwsgi]])
        context = make_context(tmp_path)
        artifact = BuildArtifact(kind="virtualenv", location="/tmp/venv")

        with pytest.raises(RuntimeError) as exc_info:
            get_deployer(context, artifact)

        message = str(exc_info.value)
        assert "No deployer found for artifact kind 'virtualenv'" in message
        # virtualenv-specific hint when uwsgi is loaded but did not accept.
        assert "uWSGI deployer is available but did not accept" in message
        assert "Available deployers: uwsgi" in message


# --- get_deployer_by_name -------------------------------------------------


class TestGetDeployerByName:
    def test_returns_named_deployer(self, install_pm, tmp_path):
        class Uwsgi:
            name = "uwsgi"

            def __init__(self, context, artifact) -> None:
                self.context = context
                self.artifact = artifact

            def accept(self) -> bool:
                return True

        install_pm(get_deployers=[[Uwsgi]])
        venv = tmp_path / "venv"
        app = types.SimpleNamespace(
            name="myapp",
            src_path=tmp_path,
            virtualenv_path=venv,
        )

        deployer = get_deployer_by_name(app, "uwsgi")

        assert isinstance(deployer, Uwsgi)
        assert deployer.context.app_name == "myapp"
        assert deployer.artifact.location == str(venv)

    def test_unknown_name_raises_with_available_list(self, install_pm):
        class Uwsgi:
            name = "uwsgi"

            def __init__(self, context, artifact) -> None:
                pass

            def accept(self) -> bool:
                return True

        install_pm(get_deployers=[[Uwsgi]])
        app = types.SimpleNamespace(name="myapp", src_path=Path("/srv/myapp"))

        with pytest.raises(RuntimeError) as exc_info:
            get_deployer_by_name(app, "docker-compose")

        message = str(exc_info.value)
        assert "Deployer 'docker-compose' not found" in message
        assert "uwsgi" in message

    def test_app_without_virtualenv_path_uses_empty_location(
        self, install_pm, tmp_path
    ):
        captured: dict[str, BuildArtifact] = {}

        class Uwsgi:
            name = "uwsgi"

            def __init__(self, context, artifact) -> None:
                captured["artifact"] = artifact

            def accept(self) -> bool:
                return True

        install_pm(get_deployers=[[Uwsgi]])
        app = types.SimpleNamespace(name="myapp", src_path=tmp_path)

        get_deployer_by_name(app, "uwsgi")

        assert captured["artifact"].location == ""


# --- get_addon ------------------------------------------------------------


class TestGetAddon:
    def test_returns_addon_matching_type(self, install_pm):
        class Postgres:
            name = "postgres"

            def __init__(self, *, addon_name) -> None:
                self.addon_name = addon_name

        install_pm(get_addons=[[Postgres]])

        addon = get_addon("postgres", "mydb")

        assert isinstance(addon, Postgres)
        assert addon.addon_name == "mydb"

    def test_unknown_addon_type_raises_with_available_addons(self, install_pm):
        class Postgres:
            name = "postgres"

            def __init__(self, *, addon_name) -> None:
                pass

        install_pm(get_addons=[[Postgres]])

        with pytest.raises(RuntimeError) as exc_info:
            get_addon("redis", "cache")

        message = str(exc_info.value)
        assert "Addon type 'redis' not found" in message
        assert "postgres" in message


# --- get_os_strategy / list_supported_os ----------------------------------


class TestOsStrategy:
    def test_returns_first_detecting_strategy(self, install_pm):
        class Debian:
            display_name = "Debian 12"

            def detect(self) -> bool:
                return False

        class RedHat:
            display_name = "RHEL 9"

            def detect(self) -> bool:
                return True

        install_pm(get_os_implementations=[[Debian, RedHat]])

        strategy = get_os_strategy()

        assert isinstance(strategy, RedHat)

    def test_no_detecting_strategy_raises_with_available_oses(self, install_pm):
        class Debian:
            display_name = "Debian 12"

            def detect(self) -> bool:
                return False

        install_pm(get_os_implementations=[[Debian]])

        with pytest.raises(RuntimeError) as exc_info:
            get_os_strategy()

        message = str(exc_info.value)
        assert "Could not detect a supported operating system" in message
        assert "Debian 12" in message

    def test_list_supported_os_returns_display_names(self, install_pm):
        class Debian:
            display_name = "Debian 12"

        class Ubuntu:
            display_name = "Ubuntu 24.04"

        install_pm(get_os_implementations=[[Debian, Ubuntu]])

        assert list_supported_os() == ["Debian 12", "Ubuntu 24.04"]

    def test_list_supported_os_defaults_when_display_name_missing(self, install_pm):
        class Bare:
            pass

        install_pm(get_os_implementations=[[Bare]])

        assert list_supported_os() == ["Unknown"]


# --- get_proxy_strategy ---------------------------------------------------


class TestGetProxyStrategy:
    def test_matches_by_class_name_substring(self, install_pm, monkeypatch):
        class NginxProxy:
            def __init__(self, app, env, workers) -> None:
                self.app = app
                self.env = env
                self.workers = workers

        install_pm(get_proxies=[[NginxProxy]])
        monkeypatch.setattr("hop3.config.HOP3_PROXY_TYPE", "nginx")

        proxy = get_proxy_strategy("app", "env", {"web": "sock"})

        assert isinstance(proxy, NginxProxy)
        assert proxy.workers == {"web": "sock"}

    def test_matches_by_name_attribute(self, install_pm, monkeypatch):
        class WeirdName:
            name = "caddy"

            def __init__(self, app, env, workers) -> None:
                pass

        install_pm(get_proxies=[[WeirdName]])
        monkeypatch.setattr("hop3.config.HOP3_PROXY_TYPE", "caddy")

        proxy = get_proxy_strategy("app", "env", {})

        assert isinstance(proxy, WeirdName)

    def test_unknown_proxy_type_raises_with_available(self, install_pm, monkeypatch):
        class NginxProxy:
            def __init__(self, app, env, workers) -> None:
                pass

        install_pm(get_proxies=[[NginxProxy]])
        monkeypatch.setattr("hop3.config.HOP3_PROXY_TYPE", "traefik")

        with pytest.raises(RuntimeError) as exc_info:
            get_proxy_strategy("app", "env", {})

        message = str(exc_info.value)
        assert "Configured proxy type 'traefik' not found" in message
        assert "NginxProxy" in message


# --- pure deployment-hint builders ----------------------------------------


class TestDeploymentHints:
    def test_docker_image_no_deployers_loaded(self):
        hints = _hints_for_docker_image([])
        assert hints == [
            "No deployers are loaded. Check your hop3-server installation."
        ]

    def test_docker_image_compose_missing(self):
        hints = _hints_for_docker_image(["uwsgi"])
        assert "The Docker Compose deployer is not loaded." in hints

    def test_docker_image_compose_present_but_rejected(self):
        hints = _hints_for_docker_image(["docker-compose"])
        assert any("did not accept" in hint for hint in hints)

    def test_virtualenv_uwsgi_missing(self):
        hints = _hints_for_virtualenv(["static"])
        assert "The uWSGI deployer is not loaded." in hints

    def test_virtualenv_uwsgi_present_but_rejected(self):
        hints = _hints_for_virtualenv(["uwsgi"])
        assert any("did not accept" in hint for hint in hints)
        assert any("Procfile" in hint for hint in hints)

    def test_static_deployer_missing(self):
        assert _hints_for_static([]) == ["The Static deployer is not loaded."]

    def test_static_deployer_present_but_rejected(self):
        assert _hints_for_static(["static"]) == [
            "The Static deployer is available but did not accept."
        ]

    def test_unknown_artifact_kind_hints(self):
        hints = _hints_for_unknown_artifact("mystery")
        assert any("'mystery' is not recognized" in hint for hint in hints)

    def test_build_deployment_hints_appends_available_deployers(self):
        hints = _build_deployment_hints("static", ["static", "uwsgi"])
        joined = "\n".join(hints)
        assert "Available deployers: static, uwsgi" in joined
        assert "hop3 system info -v" in joined

    def test_build_deployment_hints_dispatches_unknown_kind(self):
        hints = _build_deployment_hints("mystery", [])
        joined = "\n".join(hints)
        assert "'mystery' is not recognized" in joined
        # No available deployers -> the "Available deployers:" line is absent.
        assert "Available deployers:" not in joined


# --- get_plugin_manager build (re-entrancy / submodule binding) -----------


class TestGetPluginManagerBuild:
    def test_survives_preimported_plugin_submodule(self, monkeypatch):
        """Regression: importing a ``plugin.py`` before the manager is built
        binds it as a ``plugin`` *module* attribute on its parent package
        (Python import behaviour). The build must skip module-valued ``plugin``
        attrs, not re-register the submodule and crash with the order-dependent
        ``Plugin name already registered`` error. Uses redis to prove the fix is
        class-level, not WAF-specific.
        """
        # The trap the guard must avoid: importing redis.plugin (at module top)
        # bound the parent package's `.plugin` to the submodule, not an instance.
        assert inspect.ismodule(redis_pkg.plugin)

        # Force a fresh build (singleton restored by monkeypatch teardown).
        monkeypatch.setattr(plugins, "_plugin_manager", None)
        pm = get_plugin_manager()  # must not raise

        assert pm is not None
        assert pm.get_plugins()  # plugins were actually registered


# --- _iter_module_names ---------------------------------------------------


class TestIterModuleNames:
    def test_module_without_path_yields_nothing(self):
        # A plain module (not a package) has no __path__; nothing is yielded.
        names = list(_iter_module_names("hop3.core.plugins"))
        assert names == []

    def test_package_yields_submodule_names(self):
        names = list(_iter_module_names("hop3.core"))
        assert "hop3.core.plugins" in names
        assert all(name.startswith("hop3.core.") for name in names)
