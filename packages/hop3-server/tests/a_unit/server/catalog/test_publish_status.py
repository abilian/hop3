# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Publishing a catalog filed under maturity statuses (ADR 059).

The status is the *directory* a recipe lives in, and the published artefact must
not learn about that hierarchy: ADR 049 F1 pins the per-app shape ``<app-id>/…``
as the boundary that does not change, and every deployed node's loader is written
against it. So the publish step flattens, and carries the status across as a
field instead.
"""

from __future__ import annotations

import json
import tarfile

import pytest

from hop3.server.catalog.publish import (
    PublishError,
    build_index,
    generate_keypair,
    publish,
)

APP_TOML = '[metadata]\nid = "{app_id}"\ntitle = "{app_id}"\n'


def _app(root, app_id):
    d = root / app_id
    d.mkdir(parents=True)
    (d / "hop3.toml").write_text(APP_TOML.format(app_id=app_id))
    (d / "readme.md").write_text(f"# {app_id}\n")
    (d / "check.py").write_text("# smoke test\n")
    return d


def _tree(tmp_path, layout: dict[str, list[str]]):
    """Build a content dir from ``{status_or_empty: [app_id, ...]}``."""
    content = tmp_path / "content"
    for status, app_ids in layout.items():
        base = content / status if status else content
        base.mkdir(parents=True, exist_ok=True)
        for app_id in app_ids:
            _app(base, app_id)
    return content


def test_indexed_paths_are_flat_whatever_the_status(tmp_path):
    """The status directory must not appear anywhere in the published tree."""
    content = _tree(tmp_path, {"golden": ["nextcloud"], "beta": ["nextcloud-nix"]})

    built = build_index(content, serial=1)

    paths = [f["path"] for app in built.index["apps"] for f in app["files"]]
    assert "golden/nextcloud/hop3.toml" not in paths
    assert "nextcloud/hop3.toml" in paths
    assert "nextcloud-nix/hop3.toml" in paths
    assert not any(p.startswith(("golden/", "beta/")) for p in paths)


def test_the_status_travels_as_a_field(tmp_path):
    content = _tree(tmp_path, {"golden": ["nextcloud"], "beta": ["nextcloud-nix"]})

    built = build_index(content, serial=1)

    assert {a["id"]: a["status"] for a in built.index["apps"]} == {
        "nextcloud": "golden",
        "nextcloud-nix": "beta",
    }


def test_the_tarball_holds_the_flat_tree(tmp_path):
    """End to end: what a node extracts has no status directory in it."""
    _, sec_text = generate_keypair()
    content = _tree(tmp_path, {"golden": ["nextcloud"]})

    out = publish(content, sec_text, tmp_path / "dist", serial=3)

    with tarfile.open(out["tarball"]) as tar:
        names = tar.getnames()
    assert "nextcloud/hop3.toml" in names
    assert not any(n.startswith("golden/") for n in names)
    index = json.loads((tmp_path / "dist" / "index.json").read_text())
    assert index["apps"][0]["status"] == "golden"


def test_unpublishable_statuses_are_excluded_and_named(tmp_path):
    """
    Kept in the repository, kept out of the artefact — and reported.

    Being unpublished is a decision, and a decision nobody reports back is
    indistinguishable from a recipe that went missing.
    """
    content = _tree(
        tmp_path,
        {
            "golden": ["nextcloud"],
            "alpha": ["grafana"],
            "broken": ["sonarqube"],
            "retired": ["moinmoin"],
        },
    )

    built = build_index(content, serial=1)

    assert [a["id"] for a in built.index["apps"]] == ["nextcloud"]
    assert built.excluded == [
        ("grafana", "alpha"),
        ("moinmoin", "retired"),
        ("sonarqube", "broken"),
    ]


def test_a_misspelled_status_is_refused(tmp_path):
    """
    The directory IS the status, so a typo would delete apps from the catalog.

    `beeta/` is not "a status we do not publish" — it is a status nobody defined,
    and silently skipping it would drop every app beneath it.
    """
    content = _tree(tmp_path, {"golden": ["nextcloud"], "beeta": ["grafana"]})

    with pytest.raises(PublishError, match="unknown catalog status 'beeta'"):
        build_index(content, serial=1)


def test_an_empty_status_directory_is_refused(tmp_path):
    content = _tree(tmp_path, {"golden": ["nextcloud"]})
    (content / "beta").mkdir()

    with pytest.raises(PublishError, match=r"no hop3\.toml and holds no app"):
        build_index(content, serial=1)


def test_a_catalog_with_nothing_publishable_is_refused(tmp_path):
    """Signing an empty catalog would unpublish every app on every node."""
    content = _tree(tmp_path, {"alpha": ["grafana"]})

    with pytest.raises(PublishError, match="No publishable catalog apps"):
        build_index(content, serial=1)


def test_the_flat_layout_still_builds(tmp_path):
    """A checkout that predates the hierarchy keeps publishing, without a status."""
    content = _tree(tmp_path, {"": ["nextcloud"]})

    built = build_index(content, serial=1)

    assert [a["id"] for a in built.index["apps"]] == ["nextcloud"]
    assert "status" not in built.index["apps"][0]
    assert built.excluded == []


def test_the_index_is_ordered_by_id_not_by_status(tmp_path):
    """Moving a recipe between statuses must not reorder the index."""
    content = _tree(tmp_path, {"golden": ["zulip"], "beta": ["apache"]})

    built = build_index(content, serial=1)

    assert [a["id"] for a in built.index["apps"]] == ["apache", "zulip"]
