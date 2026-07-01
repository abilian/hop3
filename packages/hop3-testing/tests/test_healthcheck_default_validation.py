# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The synthesized default validation from [healthcheck] is path + status only.

An app that declares no [[test.validations]] gets one synthesized HTTP
validation derived from [healthcheck].path, asserting status 200. A body
assertion is NOT taken from [healthcheck]: the server's [healthcheck] section is
runtime liveness config (``extra="forbid"``) and rejects a ``contains`` field at
deploy time, so no deployable app can carry one there. Body assertions live in
[[test.validations]] (harness-only). These tests guard against re-introducing
the schema-invalid ``[healthcheck].contains`` plumbing.
"""

from __future__ import annotations

from pathlib import Path

from hop3_testing.catalog.loader import (
    _extract_healthcheck_from_hop3_toml,
    generate_test_definition_from_hop3_toml,
)


def test_extract_healthcheck_defaults_to_root_path():
    assert _extract_healthcheck_from_hop3_toml({}) == {"path": "/"}


def test_extract_healthcheck_reads_path_only():
    hc = _extract_healthcheck_from_hop3_toml({"healthcheck": {"path": "/h"}})
    assert hc == {"path": "/h"}


def test_healthcheck_contains_is_ignored_not_plumbed():
    # A stray [healthcheck].contains (schema-invalid; the server would reject the
    # deploy) must NOT be read into the harness's default validation.
    hc = _extract_healthcheck_from_hop3_toml({
        "healthcheck": {"path": "/h", "contains": "Hi"}
    })
    assert hc == {"path": "/h"}
    assert "contains" not in hc


def test_default_validation_is_status_only():
    td = generate_test_definition_from_hop3_toml(
        Path("apps/real-apps-native/x"),
        {"metadata": {"id": "x"}, "healthcheck": {"path": "/h"}},
    )
    http = [v for v in td.validations if v.type == "http"]
    assert len(http) == 1
    assert http[0].path == "/h"
    assert http[0].expect.contains is None


def test_body_assertion_comes_from_test_validations():
    # The correct place for a body assertion: [[test.validations]].
    td = generate_test_definition_from_hop3_toml(
        Path("apps/real-apps-native/x"),
        {
            "metadata": {"id": "x"},
            "healthcheck": {"path": "/h"},
            "test": {"validations": [{"path": "/h", "status": 200, "contains": "Hi"}]},
        },
    )
    http = [v for v in td.validations if v.type == "http"]
    assert any(v.expect.contains == "Hi" for v in http)
