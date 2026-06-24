# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the deploy preview (ADR 042 §Deploy preview)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hop3_cli.core.deploy_preview import (
    DeployPlan,
    GitState,
    _host_from_url,
    build_plan,
    domain_target_warnings,
    render_plan,
)

# ---- GitState ------------------------------------------------------------


def test_git_state_not_repo_descriptor() -> None:
    assert GitState(is_repo=False).descriptor == "(not a git repo)"


def test_git_state_descriptor_full() -> None:
    state = GitState(commit="abc123def456789", branch="main", dirty=False, is_repo=True)
    assert state.descriptor == "main @ abc123d"


def test_git_state_descriptor_dirty() -> None:
    state = GitState(commit="abcdef0", branch="feat/foo", dirty=True, is_repo=True)
    assert state.descriptor == "feat/foo @ abcdef0 (dirty)"


def test_git_state_descriptor_missing_branch() -> None:
    """Detached HEAD: branch may be empty (or 'HEAD'); descriptor still works."""
    state = GitState(commit="abcdef0", branch="", dirty=False, is_repo=True)
    assert "abcdef0" in state.descriptor


# ---- build_plan ----------------------------------------------------------


def _stub_runner(responses: dict[tuple[str, ...], str | None]):
    """Make a git_runner that returns ``responses[tuple(argv)]`` or None."""

    def run(argv: list[str], cwd) -> str | None:
        return responses.get(tuple(argv))

    return run


def test_build_plan_minimal_no_hop3_toml(tmp_path: Path) -> None:
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=tmp_path,
        context=None,
        app="myapp",
        git_runner=runner,
    )
    assert plan.app == "myapp"
    assert plan.git.is_repo is False
    assert plan.domains == ()
    assert plan.addons == ()
    assert plan.env_keys == ()


def test_build_plan_reads_top_level_domains_addons_env(tmp_path: Path) -> None:
    tmp_path.joinpath("hop3.toml").write_text(
        '[metadata]\nid = "myapp"\n'
        "\n"
        "[domains]\n"
        'list = ["a.example.com", "b.example.com"]\n'
        "\n"
        "[env]\n"
        'API_KEY = "v"\n'
        'DEBUG = "false"\n'
        '_policy = "override"\n'
        "\n"
        "[[addons]]\n"
        'type = "postgresql"\n'
        "\n"
        "[[addons]]\n"
        'type = "redis"\n'
    )
    runner = _stub_runner({
        ("git", "rev-parse", "HEAD"): "abc1234\n",
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n",
        ("git", "status", "--porcelain"): "",
    })
    plan = build_plan(
        source_path=tmp_path,
        context=None,
        app="myapp",
        git_runner=runner,
    )
    assert plan.domains == ("a.example.com", "b.example.com")
    assert set(plan.addons) == {"postgresql", "redis"}
    assert plan.env_keys == ("API_KEY", "DEBUG")  # _policy filtered out
    assert plan.git.dirty is False
    assert plan.git.commit == "abc1234"
    assert plan.git.branch == "main"


def test_build_plan_context_overrides_top_level_domains(tmp_path: Path) -> None:
    """When the active context defines domains, it FULLY REPLACES top-level."""
    tmp_path.joinpath("hop3.toml").write_text(
        '[metadata]\nid = "myapp"\n'
        "\n"
        "[domains]\n"
        'list = ["prod-only.example.com"]\n'
        "\n"
        "[contexts.staging]\n"
        'app = "myapp-staging"\n'
        'domains = ["staging.example.com", "alt-staging.example.com"]\n'
    )
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=tmp_path,
        context="staging",
        app="myapp-staging",
        git_runner=runner,
    )
    assert plan.domains == ("staging.example.com", "alt-staging.example.com")


def test_build_plan_context_env_overrides_top_level(tmp_path: Path) -> None:
    """Env keys: union of top-level and context; context overrides on collision."""
    tmp_path.joinpath("hop3.toml").write_text(
        '[metadata]\nid = "x"\n'
        "\n"
        "[env]\n"
        'API_KEY = "base"\n'
        'BASE_ONLY = "x"\n'
        "\n"
        "[contexts.staging]\n"
        'app = "x"\n'
        "[contexts.staging.env]\n"
        'API_KEY = "ctx"\n'
        'CTX_ONLY = "y"\n'
    )
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=tmp_path,
        context="staging",
        app="x",
        git_runner=runner,
    )
    assert set(plan.env_keys) == {"API_KEY", "BASE_ONLY", "CTX_ONLY"}


def test_build_plan_context_with_empty_domains_list(tmp_path: Path) -> None:
    """``[contexts.foo].domains = []`` is an explicit no-domains override."""
    tmp_path.joinpath("hop3.toml").write_text(
        '[metadata]\nid = "x"\n'
        "\n"
        "[domains]\n"
        'list = ["prod.example.com"]\n'
        "\n"
        "[contexts.staging]\n"
        'app = "x"\n'
        "domains = []\n"
    )
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=tmp_path,
        context="staging",
        app="x",
        git_runner=runner,
    )
    assert plan.domains == ()


def test_build_plan_dirty_git_detected(tmp_path: Path) -> None:
    runner = _stub_runner({
        ("git", "rev-parse", "HEAD"): "abc1234\n",
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): "wip\n",
        ("git", "status", "--porcelain"): " M file.txt\n",
    })
    plan = build_plan(
        source_path=tmp_path,
        context=None,
        app="x",
        git_runner=runner,
    )
    assert plan.git.dirty is True


def test_build_plan_legacy_provider_section(tmp_path: Path) -> None:
    """Fall back to ``[[provider]]`` when ``[[addons]]`` is absent."""
    tmp_path.joinpath("hop3.toml").write_text(
        '[metadata]\nid = "x"\n\n[[provider]]\ntype = "postgresql"\n'
    )
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=tmp_path,
        context=None,
        app="x",
        git_runner=runner,
    )
    assert plan.addons == ("postgresql",)


def test_build_plan_ignores_ancestor_hop3_toml_for_metadata(tmp_path: Path) -> None:
    """The deploy archive only packages source_path; an ancestor's
    hop3.toml is never sent to the server. The preview MUST NOT pretend
    otherwise — domains/addons come from source_path's hop3.toml only.

    (If we walked upward, the preview would advertise domains/addons
    that the server never actually sees.)
    """
    tmp_path.joinpath("hop3.toml").write_text(
        '[metadata]\nid = "myapp"\n'
        "[domains]\n"
        'list = ["a.example.com", "b.example.com"]\n'
        "[[addons]]\n"
        'type = "postgresql"\n'
    )
    subdir = tmp_path / "deep" / "subdir"
    subdir.mkdir(parents=True)
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=subdir,
        context=None,
        app="myapp",
        home=tmp_path.parent,
        git_runner=runner,
    )
    # source_path/hop3.toml doesn't exist → empty metadata. NOT walked.
    assert plan.domains == ()
    assert plan.addons == ()
    # But the ancestor diagnostic captures the discrepancy.
    assert plan.ancestor_hop3_toml == (tmp_path / "hop3.toml").resolve()


def test_build_plan_no_ancestor_warning_when_source_has_own(tmp_path: Path) -> None:
    """When source_path itself has hop3.toml, no ancestor warning fires
    (we'd be warning about a non-issue).
    """
    tmp_path.joinpath("hop3.toml").write_text('[metadata]\nid = "x"\n')
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    subdir.joinpath("hop3.toml").write_text('[metadata]\nid = "y"\n')
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=subdir,
        context=None,
        app="y",
        home=tmp_path.parent,
        git_runner=runner,
    )
    assert plan.ancestor_hop3_toml is None


def test_render_plan_surfaces_ancestor_warning(tmp_path: Path) -> None:
    """The diagnostic must appear in the preview output so an operator
    notices the deploy-from-subdir footgun.
    """
    out = render_plan(
        _plan(
            source_path=tmp_path / "subdir",
            ancestor_hop3_toml=tmp_path / "hop3.toml",
        )
    )
    assert "has no hop3.toml" in out
    assert "ancestor at" in out
    assert "NOT be included" in out


def test_build_plan_ancestor_walk_stops_at_home(tmp_path: Path) -> None:
    """The ancestor-diagnostic walk stops at home — a hop3.toml above
    home doesn't trigger the warning.
    """
    tmp_path.joinpath("hop3.toml").write_text('[metadata]\nid = "above-home"\n')
    home = tmp_path / "home"
    cwd = home / "subproject"
    cwd.mkdir(parents=True)
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=cwd,
        context=None,
        app="myapp",
        home=home,
        git_runner=runner,
    )
    assert plan.ancestor_hop3_toml is None


def test_build_plan_unparseable_hop3_toml_safe(tmp_path: Path) -> None:
    """Broken TOML in source dir should not raise; treat as empty."""
    tmp_path.joinpath("hop3.toml").write_text("not [ valid toml")
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=tmp_path,
        context=None,
        app="x",
        git_runner=runner,
    )
    assert plan.domains == ()
    assert plan.addons == ()
    assert plan.env_keys == ()


# ---- render_plan ---------------------------------------------------------


def _plan(**overrides) -> DeployPlan:
    defaults: dict[str, Any] = {
        "source_path": Path("/tmp/proj"),
        "git": GitState(is_repo=False),
        "context": None,
        "app": "myapp",
        "domains": (),
        "addons": (),
        "env_keys": (),
        "ancestor_hop3_toml": None,
    }
    defaults.update(overrides)
    return DeployPlan(**defaults)


def test_render_plan_minimal() -> None:
    out = render_plan(_plan())
    assert out.startswith("About to deploy:")
    assert "Source:" in out
    assert "App:      myapp" in out
    assert "Context:  (none)" in out
    assert "Domains:  (none)" in out
    assert "Addons:   (none)" in out
    assert "Env vars: (none)" in out


def test_render_plan_full() -> None:
    out = render_plan(
        _plan(
            context="staging",
            domains=("a.example.com", "b.example.com"),
            addons=("postgresql",),
            env_keys=("API_KEY", "DEBUG"),
            git=GitState(commit="abc1234", branch="main", dirty=False, is_repo=True),
        )
    )
    assert "Context:  staging" in out
    assert "Domains:  a.example.com, b.example.com" in out
    assert "Addons:   postgresql" in out
    assert "Env vars: API_KEY, DEBUG" in out


def test_render_plan_dirty_git_emits_warning() -> None:
    out = render_plan(
        _plan(git=GitState(commit="abc1234", branch="wip", dirty=True, is_repo=True))
    )
    assert "warning: source tree has uncommitted changes" in out


def test_render_plan_clean_git_no_warning() -> None:
    out = render_plan(
        _plan(git=GitState(commit="abc1234", branch="main", dirty=False, is_repo=True))
    )
    assert "warning" not in out


@pytest.mark.parametrize(
    ("env_keys", "expected_segment"),
    [
        ((), "Env vars: (none)"),
        (("B", "A"), "Env vars: A, B"),  # sorted in render
    ],
)
def test_render_plan_env_summary(env_keys, expected_segment) -> None:
    out = render_plan(_plan(env_keys=env_keys))
    assert expected_segment in out


# ---- HOST_NAME-derived domains -------------------------------------------


def test_build_plan_includes_host_name_env_as_domain(tmp_path: Path) -> None:
    """An app that declares its domain only via [env].HOST_NAME (the legacy
    shape) must still surface it — otherwise the preview shows '(none)' and the
    DNS host-check is silently skipped."""
    tmp_path.joinpath("hop3.toml").write_text(
        '[metadata]\nid = "edrix"\n\n[env]\nHOST_NAME = "edrix.eu"\n'
    )
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(
        source_path=tmp_path, context=None, app="edrix", git_runner=runner
    )
    assert "edrix.eu" in plan.domains


def test_build_plan_host_name_multi_and_dedup(tmp_path: Path) -> None:
    """HOST_NAME may list several hosts; the catch-all '_' and duplicates of a
    [domains].list entry are dropped."""
    tmp_path.joinpath("hop3.toml").write_text(
        '[metadata]\nid = "a"\n\n'
        "[domains]\n"
        'list = ["a.example.com"]\n\n'
        "[env]\n"
        'HOST_NAME = "a.example.com b.example.com _"\n'
    )
    runner = _stub_runner({("git", "rev-parse", "HEAD"): None})
    plan = build_plan(source_path=tmp_path, context=None, app="a", git_runner=runner)
    assert plan.domains == ("a.example.com", "b.example.com")  # deduped, no "_"


# ---- DNS host-check ------------------------------------------------------


def _resolver(mapping: dict[str, set[str]]):
    """Stub resolver: returns mapping[host] or an empty set (unresolvable)."""
    return lambda host: mapping.get(host, set())


def test_domain_target_warning_on_mismatch() -> None:
    """The edrix bug: domain points at a different server than the deploy
    target — every request 502s while the app looks healthy."""
    warnings = domain_target_warnings(
        ("edrix.eu",),
        "ssh://root@hop3.dev",
        resolver=_resolver({
            "hop3.dev": {"135.181.203.156"},
            "edrix.eu": {"95.217.187.164"},
        }),
    )
    assert len(warnings) == 1
    assert "edrix.eu" in warnings[0]
    assert "95.217.187.164" in warnings[0]
    assert "hop3.dev" in warnings[0]
    assert "135.181.203.156" in warnings[0]
    assert "CDN" in warnings[0]  # don't cry wolf on intentional proxying


def test_domain_target_no_warning_when_ips_overlap() -> None:
    warnings = domain_target_warnings(
        ("app.example.com",),
        "ssh://root@srv",
        resolver=_resolver({"srv": {"1.2.3.4", "::1"}, "app.example.com": {"1.2.3.4"}}),
    )
    assert warnings == []


def test_domain_target_skips_unresolvable_domain() -> None:
    """A domain that doesn't resolve (not registered yet, internal) is skipped,
    not warned — we never guess."""
    warnings = domain_target_warnings(
        ("not-registered.example",),
        "https://srv:8000",
        resolver=_resolver({"srv": {"1.2.3.4"}}),
    )
    assert warnings == []


def test_domain_target_no_warning_when_target_unresolvable() -> None:
    warnings = domain_target_warnings(
        ("app.example.com",),
        "ssh://root@unknown-host",
        resolver=_resolver({"app.example.com": {"9.9.9.9"}}),
    )
    assert warnings == []


def test_domain_target_skips_when_domain_equals_target() -> None:
    warnings = domain_target_warnings(
        ("hop3.dev",),
        "ssh://root@hop3.dev",
        resolver=_resolver({"hop3.dev": {"135.181.203.156"}}),
    )
    assert warnings == []


def test_domain_target_no_api_url() -> None:
    assert domain_target_warnings(("edrix.eu",), None, resolver=_resolver({})) == []


@pytest.mark.parametrize(
    ("api_url", "expected"),
    [
        ("ssh://root@hop3.dev", "hop3.dev"),
        ("ssh://root@hop3.dev:22", "hop3.dev"),
        ("http://example.com:8000", "example.com"),
        ("https://example.com", "example.com"),
        ("hop3.dev:8000", "hop3.dev"),
        ("root@hop3.dev", "hop3.dev"),
        ("", ""),
        (None, ""),
    ],
)
def test_host_from_url(api_url, expected) -> None:
    assert _host_from_url(api_url) == expected
