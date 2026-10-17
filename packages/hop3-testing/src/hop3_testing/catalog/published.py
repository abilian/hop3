# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The tests of a published catalog, read from the server that installs it.

`hop3-test run --recipes published` tests what an operator installs. The server
refreshes its signed catalog. Each test comes from the server's extracted copy
of the recipe, so it describes the recipe `hop3 catalog install` deploys.
The local checkout plays no part, except to size the server's features before
it exists.
"""

from __future__ import annotations

import base64
import io
import json
import shlex
import subprocess
import tarfile
from typing import TYPE_CHECKING

from hop3_testing.targets.constants import hermetic_cli_cwd

from .loader import load_test_definition_smart

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from hop3_testing.targets.base import DeploymentTarget

    from .models import TestDefinition

#: What the catalog publishes; `alpha` and below never leave the repository.
PUBLISHED_STATUSES = ("golden", "beta")

#: The server's verified catalog (`hop3.config.CATALOG_ROOT`).
SERVER_CATALOG_ROOT = "/home/hop3/catalog"

#: Not needed to test a recipe, and most of the bytes.
_FETCH_EXCLUDES = ("*/screenshots", "*/icon.*")


class PublishedCatalogError(RuntimeError):
    """The published catalog could not be refreshed, read or selected from."""


def published_tests(
    target: DeploymentTarget,
    statuses: Sequence[str],
    names: Sequence[str],
    into: Path,
) -> list[TestDefinition]:
    """
    Refresh the target's catalog and load the tests of the selected entries.

    Entries are selected by status and, when ``names`` is given, by id; a
    name the catalog does not publish is an error. Each entry is copied from
    the server into ``into/<id>`` and its test marked to deploy with
    `hop3 catalog install`.
    """
    _refresh(target)
    index = _read_index(target)
    ids = select_ids(index, statuses, names)
    _fetch(target, ids, into)
    tests = []
    for app_id in ids:
        test = load_test_definition_smart(into / app_id)
        test.catalog_id = app_id
        tests.append(test)
    return tests


def select_ids(index: dict, statuses: Sequence[str], names: Sequence[str]) -> list[str]:
    """The ids of the index's entries in ``statuses``, narrowed to ``names``."""
    entries = {e["id"]: e.get("status", "") for e in index.get("apps", [])}
    unknown = sorted(set(names) - entries.keys())
    if unknown:
        msg = (
            f"Not in the published catalog: {', '.join(unknown)}. "
            "`hop3 catalog list` shows what the server publishes."
        )
        raise PublishedCatalogError(msg)
    ids = sorted(
        app_id
        for app_id, status in entries.items()
        if status in statuses and (not names or app_id in names)
    )
    if not ids:
        msg = (
            f"The published catalog has no entry with status "
            f"{' or '.join(statuses)}"
            + (f" among {', '.join(names)}" if names else "")
            + "."
        )
        raise PublishedCatalogError(msg)
    return ids


def _refresh(target: DeploymentTarget) -> None:
    """`hop3 catalog refresh`, as an operator runs it; its failure is fatal."""
    result = subprocess.run(
        ["hop3", "catalog", "refresh"],
        env=target.cli_env(),
        cwd=hermetic_cli_cwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or "refresh failed" in output:
        msg = (
            f"`hop3 catalog refresh` failed (exit {result.returncode}): {output[:500]}"
        )
        raise PublishedCatalogError(msg)


def _read_index(target: DeploymentTarget) -> dict:
    """The signed index of the catalog the server just published."""
    path = f"{SERVER_CATALOG_ROOT}/index.json"
    code, out, err = target.exec_run(["cat", path])
    if code != 0:
        msg = f"Could not read {path} on the server (exit {code}): {err.strip()[:300]}"
        raise PublishedCatalogError(msg)
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        msg = f"{path} on the server is not JSON: {out[:300]!r}"
        raise PublishedCatalogError(msg) from e


def _fetch(target: DeploymentTarget, ids: Sequence[str], into: Path) -> None:
    """
    Copy the entries' recipes from the server into ``into``.

    Base64 over the target's text channel: `exec_run` returns decoded text.
    """
    excludes = " ".join(f"--exclude={shlex.quote(p)}" for p in _FETCH_EXCLUDES)
    command = (
        f"tar czf - -C {SERVER_CATALOG_ROOT} {excludes} {shlex.join(ids)} | base64 -w0"
    )
    code, out, err = target.exec_run(["sh", "-c", command])
    if code != 0:
        msg = f"Could not copy the recipes from the server (exit {code}): {err.strip()[:300]}"
        raise PublishedCatalogError(msg)
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(out)), mode="r:gz") as tar:
        tar.extractall(into, filter="data")
