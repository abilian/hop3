# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Context flatten-on-deploy (ADR 042 r2, step E1).

When a context is selected, the deploy uploads a hop3.toml with the context's
env/domains merged into the top level and all ``[contexts.*]`` stripped — the
same ``flatten_for_context`` the preview uses, so preview == deploy.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import tomllib
from hop3_cli.commands.arguments import generate_archive
from hop3_cli.core.deploy_preview import build_plan, flatten_for_context
from hop3_cli.main import _context_deploy_override

# ---- flatten_for_context ----


def test_flatten_merges_env_and_replaces_domains():
    data = {
        "metadata": {"id": "m"},
        "domains": {"list": ["base.com"]},
        "env": {"LOG": "info", "KEEP": "1"},
        "contexts": {
            "prod": {
                "server": "s",
                "app": "m-prod",
                "domains": {"list": ["prod.com"]},
                "env": {"LOG": "warn"},
            }
        },
    }
    eff = flatten_for_context(data, "prod")
    assert eff["domains"] == {"list": ["prod.com"]}  # full-replace
    assert eff["env"] == {"LOG": "warn", "KEEP": "1"}  # merge, context wins
    assert "contexts" not in eff  # stripped


def test_flatten_no_context_strips_contexts_only():
    data = {"env": {"A": "1"}, "contexts": {"prod": {"server": "s"}}}
    eff = flatten_for_context(data, None)
    assert "contexts" not in eff
    assert eff["env"] == {"A": "1"}


def test_flatten_tolerates_bare_list_domains():
    data = {"contexts": {"prod": {"server": "s", "domains": ["x.com"]}}}
    eff = flatten_for_context(data, "prod")
    assert eff["domains"] == {"list": ["x.com"]}


def test_flatten_context_without_domains_inherits_top_level():
    data = {
        "domains": {"list": ["base.com"]},
        "contexts": {"prod": {"server": "s", "env": {"A": "1"}}},
    }
    eff = flatten_for_context(data, "prod")
    assert eff["domains"] == {"list": ["base.com"]}


def test_flatten_does_not_mutate_input():
    data = {"contexts": {"prod": {"server": "s"}}}
    flatten_for_context(data, "prod")
    assert "contexts" in data  # original untouched


# ---- preview reflects the flatten (preview == deploy) ----


def test_build_plan_reflects_context_merge(tmp_path):
    (tmp_path / "hop3.toml").write_text(
        '[metadata]\nid="m"\n[domains]\nlist=["base.com"]\n[env]\nLOG="info"\n'
        '[contexts.prod]\nserver="s"\napp="m-prod"\n'
        '[contexts.prod.domains]\nlist=["prod.com"]\n'
        '[contexts.prod.env]\nLOG="warn"\nEXTRA="1"\n'
    )
    plan = build_plan(source_path=tmp_path, context="prod", app="m-prod")
    assert plan.domains == ("prod.com",)
    assert set(plan.env_keys) == {"LOG", "EXTRA"}


# ---- tar substitution ----


def test_generate_archive_substitutes_hop3_toml(tmp_path):
    (tmp_path / "hop3.toml").write_text('[metadata]\nid="orig"\n')
    (tmp_path / "app.py").write_text("x = 1\n")
    override = b'[metadata]\nid = "flattened"\n'
    tgz = generate_archive(tmp_path, hop3_toml_override=override)
    with tarfile.open(fileobj=io.BytesIO(tgz), mode="r:gz") as tar:
        content = tar.extractfile("hop3.toml").read()
    assert content == override
    # The committed on-disk file is untouched.
    assert "orig" in (tmp_path / "hop3.toml").read_text()


# ---- _context_deploy_override (the main.py wiring) ----


def test_deploy_override_flattens_for_context():
    Path("hop3.toml").write_text(
        '[metadata]\nid="m"\n[env]\nA="1"\n[contexts.prod]\nserver="s"\n'
        '[contexts.prod.env]\nA="2"\n'
    )
    ov = _context_deploy_override(["deploy"], SimpleNamespace(context="prod"))
    eff = tomllib.loads(ov.decode())
    assert "contexts" not in eff
    assert eff["env"] == {"A": "2"}


def test_deploy_override_none_for_non_deploy():
    assert _context_deploy_override(["apps"], SimpleNamespace(context="prod")) is None


def test_deploy_override_none_without_hop3_toml():
    assert _context_deploy_override(["deploy"], SimpleNamespace(context="prod")) is None
