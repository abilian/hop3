# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the plugin manager helper logic in ``hop3.core.plugins``.

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
import hop3.plugins.redis.plugin  # ruff:ignore[unused-import] — binds redis_pkg.plugin attribute
from hop3.config import HopConfig
from hop3.core import plugins
from hop3.core.artifacts import ARTIFACT_FILENAME
from hop3.core.plugins import (
    NeverBuiltError,
    get_addon,
    get_builder,
    get_deployer,
    get_os_strategy,
    get_plugin_manager,
    get_probe_deployer,
    get_proxy_strategy,
    list_supported_os,
)
from hop3.core.protocols import BuildArtifact, DeploymentContext
from hop3.lib.console import Abort

# --- Test doubles ---------------------------------------------------------


class StubHook:
    """
    A pluggy-like ``pm.hook`` whose hook calls return preset lists-of-lists.

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
    """
    Install a stub PluginManager as the module singleton.

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


def make_builder(builder_name: str, accepts: bool, fallback_: bool = False) -> type:
    """A builder class called ``builder_name`` whose accept() answers ``accepts``."""

    class FakeBuilder:
        name = builder_name
        fallback = fallback_

        def __init__(self, context) -> None:
            self.context = context
            self.rejection_reason = f"{builder_name} declined"

        def accept(self) -> bool:
            return accepts

    return FakeBuilder


# --- get_builder ----------------------------------------------------------


class TestGetBuilder:
    def test_auto_detects_first_accepting_builder(self, install_pm, tmp_path):
        class Accepting:
            name = "accepting"
            fallback = False

            def __init__(self, context) -> None:
                self.context = context

            def accept(self) -> bool:
                return True

        class Rejecting:
            name = "rejecting"
            fallback = False

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
            fallback = False

            def __init__(self, context) -> None:
                pass

            def accept(self) -> bool:
                return False

            rejection_reason = "no Procfile here"

        install_pm(get_builders=[[Picky]])
        context = make_context(tmp_path)

        with pytest.raises(Abort) as exc_info:
            get_builder(context)

        message = str(exc_info.value)
        assert "no builder recognises the source" in message
        assert "picky: no Procfile here" in message
        assert "[build].builder to one of: picky" in message
        # The core names no language files: the reasons come from the plugins.
        assert "requirements.txt" not in message

    def test_builder_constructor_error_is_recorded_in_message(
        self, install_pm, tmp_path
    ):
        class Exploding:
            name = "exploding"
            fallback = False

            def __init__(self, context) -> None:
                msg = "boom"
                raise ValueError(msg)

            def accept(self) -> bool:
                return True

        install_pm(get_builders=[[Exploding]])
        context = make_context(tmp_path)

        with pytest.raises(Abort) as exc_info:
            get_builder(context)

        message = str(exc_info.value)
        assert "'exploding' builder" in message
        assert "ValueError: boom" in message

    def test_explicit_builder_selected_by_name(self, install_pm, tmp_path):
        accept_calls: list[str] = []

        class Local:
            name = "local"
            fallback = False

            def __init__(self, context) -> None:
                self.context = context

            def accept(self) -> bool:
                accept_calls.append("local")
                return True

        class Docker:
            name = "docker"
            fallback = False

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
            fallback = False

            def __init__(self, context) -> None:
                pass

            def accept(self) -> bool:
                return True

        install_pm(get_builders=[[Local]])
        context = make_context(
            tmp_path, {"hop3_config": {"build": {"builder": "nonexistent"}}}
        )

        with pytest.raises(Abort) as exc_info:
            get_builder(context)

        message = str(exc_info.value)
        assert "no builder named 'nonexistent' is loaded (loaded: local)" in message
        assert "[build].builder to one of: local" in message

    def test_non_dict_hop3_config_falls_back_to_auto_detect(self, install_pm, tmp_path):
        class Accepting:
            name = "accepting"
            fallback = False

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
            fallback = False

            def __init__(self, context) -> None:
                pass

            def accept(self) -> bool:
                return True

        install_pm(get_builders=[[Accepting]])
        # build_config is present but not a dict -> builder name forced to "auto".
        context = make_context(tmp_path, {"hop3_config": {"build": "not-a-dict"}})

        builder = get_builder(context)

        assert isinstance(builder, Accepting)

    def test_two_accepting_builders_abort_naming_both(self, install_pm, tmp_path):
        """A Dockerfile beside a hop3.nix used to build with Docker, silently."""
        docker, nix = make_builder("docker", True), make_builder("nix", True)
        install_pm(get_builders=[[docker], [nix], [make_builder("local", True, True)]])

        with pytest.raises(Abort) as exc_info:
            get_builder(make_context(tmp_path))

        message = str(exc_info.value)
        assert "several builders accept the app: docker, nix" in message
        assert "set [build].builder in hop3.toml to one of: docker, nix" in message

    def test_a_fallback_builder_yields_to_a_specific_one(self, install_pm, tmp_path):
        local = make_builder("local", True, True)
        docker = make_builder("docker", True)
        install_pm(get_builders=[[local], [docker]])

        assert isinstance(get_builder(make_context(tmp_path)), docker)

    def test_a_fallback_builder_is_chosen_alone(self, install_pm, tmp_path):
        local = make_builder("local", True, True)
        install_pm(get_builders=[[make_builder("docker", False)], [local]])

        assert isinstance(get_builder(make_context(tmp_path)), local)

    def test_an_accept_that_raises_aborts_instead_of_moving_on(
        self, install_pm, tmp_path
    ):
        class Crashing:
            name = "crashing"
            fallback = False

            def __init__(self, context) -> None:
                pass

            def accept(self) -> bool:
                msg = "probe bug"
                raise KeyError(msg)

        install_pm(get_builders=[[Crashing], [make_builder("local", True, True)]])

        with pytest.raises(Abort, match="probe bug"):
            get_builder(make_context(tmp_path))

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
        artifact = BuildArtifact(
            kind="virtualenv", builder="local", location="/tmp/venv"
        )

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
        artifact = BuildArtifact(
            kind="virtualenv", builder="local", location="/tmp/venv"
        )

        with pytest.raises(Abort) as exc_info:
            get_deployer(context, artifact)

        message = str(exc_info.value)
        assert "no loaded deployer accepts a 'virtualenv' artifact" in message
        assert "(loaded: uwsgi)" in message

    def test_two_accepting_deployers_abort(self, install_pm, tmp_path):
        class Uwsgi:
            name = "uwsgi"

            def __init__(self, context, artifact) -> None:
                pass

            def accept(self) -> bool:
                return True

        class Other(Uwsgi):
            name = "other"

        install_pm(get_deployers=[[Uwsgi], [Other]])
        artifact = BuildArtifact(kind="python", builder="local", location="/tmp/venv")

        with pytest.raises(Abort) as exc_info:
            get_deployer(make_context(tmp_path), artifact)

        message = str(exc_info.value)
        assert "several deployers accept a 'python' artifact: uwsgi, other" in message
        assert "[deploy].deployer" in message

    def test_explicit_deployer_selected_by_name(self, install_pm, tmp_path):
        accept_calls: list[str] = []

        class Uwsgi:
            name = "uwsgi"

            def __init__(self, context, artifact) -> None:
                self.context = context
                self.artifact = artifact

            def accept(self) -> bool:
                accept_calls.append("uwsgi")
                return True

        class Compose:
            name = "docker-compose"

            def __init__(self, context, artifact) -> None:
                self.context = context
                self.artifact = artifact

            def accept(self) -> bool:
                accept_calls.append("docker-compose")
                return True

        install_pm(get_deployers=[[Uwsgi, Compose]])
        context = make_context(
            tmp_path, {"hop3_config": {"deploy": {"deployer": "docker-compose"}}}
        )
        artifact = BuildArtifact(
            kind="virtualenv", builder="local", location="/tmp/venv"
        )

        deployer = get_deployer(context, artifact)

        assert isinstance(deployer, Compose)
        # Explicit selection must not auto-detect (accept() never called).
        assert accept_calls == []

    def test_explicit_deployer_not_found_raises(self, install_pm, tmp_path):
        class Uwsgi:
            name = "uwsgi"

            def __init__(self, context, artifact) -> None:
                pass

            def accept(self) -> bool:
                return True

        install_pm(get_deployers=[[Uwsgi]])
        context = make_context(
            tmp_path, {"hop3_config": {"deploy": {"deployer": "nonexistent"}}}
        )
        artifact = BuildArtifact(
            kind="virtualenv", builder="local", location="/tmp/venv"
        )

        with pytest.raises(Abort) as exc_info:
            get_deployer(context, artifact)

        message = str(exc_info.value)
        assert "no deployer named 'nonexistent' is loaded (loaded: uwsgi)" in message


# --- get_probe_deployer -------------------------------------------------


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
        app = make_built_app(tmp_path, kind="docker-image", location="hop3/myapp:7")

        deployer = get_probe_deployer(app, "uwsgi")

        assert isinstance(deployer, Uwsgi)
        assert deployer.context.app_name == "myapp"
        # The last deploy's artifact, not a placeholder of kind "unknown".
        assert deployer.artifact.kind == "docker-image"
        assert deployer.artifact.location == "hop3/myapp:7"

    def test_a_malformed_hop3_toml_does_not_break_the_probe(self, install_pm, tmp_path):
        """A running app with a syntax error in hop3.toml still reports status."""
        install_pm(get_deployers=[[Uwsgi]])
        app = make_built_app(tmp_path, kind="docker-image", location="hop3/myapp:7")
        (app.app_path / "hop3.toml").write_text("[build\n")
        (app.src_path / "hop3.toml").write_text("[build\n")

        deployer = get_probe_deployer(app, "uwsgi")

        assert deployer.context.app_config == {}

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
            get_probe_deployer(app, "docker-compose")

        message = str(exc_info.value)
        assert "Deployer 'docker-compose' not found" in message
        assert "uwsgi" in message

    def test_a_never_built_app_raises_never_built(self, install_pm, tmp_path):
        install_pm(get_deployers=[[Uwsgi]])
        app = types.SimpleNamespace(name="myapp", app_path=tmp_path, src_path=tmp_path)

        with pytest.raises(NeverBuiltError, match="never built"):
            get_probe_deployer(app, "uwsgi")

    def test_a_damaged_artifact_is_an_error(self, install_pm, tmp_path):
        install_pm(get_deployers=[[Uwsgi]])
        (tmp_path / ARTIFACT_FILENAME).write_text("{not json")
        app = types.SimpleNamespace(name="myapp", app_path=tmp_path, src_path=tmp_path)

        with pytest.raises(RuntimeError, match="is unreadable") as e:
            get_probe_deployer(app, "uwsgi")
        assert not isinstance(e.value, NeverBuiltError)


class Uwsgi:
    name = "uwsgi"

    def __init__(self, context, artifact) -> None:
        self.context = context
        self.artifact = artifact


def make_built_app(app_path: Path, *, kind: str, location: str):
    """An app directory with a saved artifact and a hop3.toml, as after a deploy."""
    src = app_path / "src"
    src.mkdir()
    (src / "hop3.toml").write_text("[docker]\nport = 8080\n")
    BuildArtifact(kind=kind, builder="docker", location=location).save(
        app_path / ARTIFACT_FILENAME
    )
    return types.SimpleNamespace(name="myapp", app_path=app_path, src_path=src)


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

        with pytest.raises(Abort) as exc_info:
            get_os_strategy()

        message = str(exc_info.value)
        assert "no OS strategy recognises this host" in message
        assert "Debian 12" in message

    def test_two_detecting_strategies_abort(self, install_pm):
        class Debian:
            def detect(self) -> bool:
                return True

        class Ubuntu(Debian):
            pass

        install_pm(get_os_implementations=[[Debian], [Ubuntu]])

        with pytest.raises(Abort, match="several OS strategies claim this host"):
            get_os_strategy()

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
    def test_matches_by_name(self, install_pm, monkeypatch):
        class Whatever:
            name = "caddy"

            def __init__(self, app, env, workers) -> None:
                self.workers = workers

        install_pm(get_proxies=[[Whatever]])
        monkeypatch.setattr(
            HopConfig, "HOP3_PROXY_TYPE", property(lambda _self: "Caddy")
        )

        proxy = get_proxy_strategy("app", "env", {"web": "sock"})

        assert isinstance(proxy, Whatever)
        assert proxy.workers == {"web": "sock"}

    def test_a_class_name_containing_the_type_is_no_match(
        self, install_pm, monkeypatch
    ):
        """`proxy_type in class_name` once let "nginx" pick NginxCompatProxy."""

        class NginxCompatProxy:
            name = "nginx-compat"

            def __init__(self, app, env, workers) -> None:
                pass

        install_pm(get_proxies=[[NginxCompatProxy]])
        monkeypatch.setattr(
            HopConfig, "HOP3_PROXY_TYPE", property(lambda _self: "nginx")
        )

        with pytest.raises(Abort) as exc_info:
            get_proxy_strategy("app", "env", {})

        message = str(exc_info.value)
        assert "no proxy named 'nginx' is loaded (loaded: nginx-compat)" in message
        assert "HOP3_PROXY_TYPE" in message

    def test_the_real_proxies_are_selected_by_name(self, monkeypatch):
        monkeypatch.setattr(plugins, "_plugin_manager", None)
        for name in ("nginx", "caddy", "traefik"):
            monkeypatch.setattr(
                HopConfig, "HOP3_PROXY_TYPE", property(lambda _self, n=name: n)
            )
            assert plugins.get_proxy_class().name == name


# --- get_plugin_manager build (re-entrancy / submodule binding) -----------


class TestGetPluginManagerBuild:
    def test_survives_preimported_plugin_submodule(self, monkeypatch):
        """
        Regression: importing a ``plugin.py`` before the manager is built
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

    def test_a_reexported_plugin_instance_registers_once(self, monkeypatch):
        """An ``__init__`` doing ``from .plugin import plugin`` used to crash."""

        class Mine:
            name = "mine"

        instance = Mine()
        package = types.ModuleType("fake_pkg")
        package.plugin = instance  # ty: ignore[unresolved-attribute]
        module = types.ModuleType("fake_pkg.plugin")
        module.plugin = instance  # ty: ignore[unresolved-attribute]
        monkeypatch.setattr(plugins, "get_core_plugins", lambda: [package, module])
        monkeypatch.setattr(plugins, "_plugin_manager", None)

        pm = get_plugin_manager()

        assert pm.get_plugin("mine") is instance

    def test_two_plugins_claiming_one_name_still_raise(self, monkeypatch):
        class Mine:
            name = "mine"

        first, second = types.ModuleType("a"), types.ModuleType("b")
        first.plugin = Mine()  # ty: ignore[unresolved-attribute]
        second.plugin = Mine()  # ty: ignore[unresolved-attribute]
        monkeypatch.setattr(plugins, "get_core_plugins", lambda: [first, second])
        monkeypatch.setattr(plugins, "_plugin_manager", None)

        with pytest.raises(ValueError, match="mine"):
            get_plugin_manager()

    def test_a_plugin_under_the_wrong_entry_point_group_aborts(self, monkeypatch):
        dist = types.SimpleNamespace(name="my-hop3-plugin")
        wrong = types.SimpleNamespace(
            group="hop3.plugins", name="mine", value="my_plugin:plugin", dist=dist
        )
        monkeypatch.setattr(
            plugins,
            "entry_points",
            lambda group: [wrong] if group == "hop3.plugins" else [],
        )
        monkeypatch.setattr(plugins, "_plugin_manager", None)

        with pytest.raises(Abort) as exc_info:
            get_plugin_manager()

        message = str(exc_info.value)
        assert "my-hop3-plugin (hop3.plugins: mine = my_plugin:plugin)" in message
        assert '[project.entry-points."hop3"]' in message


class TestRealBuilders:
    """The shipped builders, through the real plugin manager."""

    def test_dockerfile_and_hop3_nix_together_abort(self, monkeypatch, tmp_path):
        monkeypatch.setattr(plugins, "_plugin_manager", None)
        (tmp_path / "Dockerfile").write_text("FROM scratch\n")
        (tmp_path / "hop3.nix").write_text("{}\n")
        # The Nix builder refuses an app on a server without Nix before it
        # can accept; this test is about the choice between builders.
        monkeypatch.setattr(
            "hop3.plugins.build.nix.builder.NixBuilder._require_nix", lambda self: None
        )

        with pytest.raises(Abort, match="several builders accept the app: docker, nix"):
            get_builder(make_context(tmp_path))

    def test_dockerfile_beside_python_source_builds_with_docker(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(plugins, "_plugin_manager", None)
        (tmp_path / "Dockerfile").write_text("FROM scratch\n")
        (tmp_path / "requirements.txt").write_text("flask\n")

        assert get_builder(make_context(tmp_path)).name == "docker"
