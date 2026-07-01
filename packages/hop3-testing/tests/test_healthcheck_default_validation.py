# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""[healthcheck] drives the synthesized default validation (path + optional body).

An app that declares no [[test.validations]] gets one synthesized HTTP
validation from [healthcheck]: it probes [healthcheck].path (default "/") and,
when [healthcheck].contains is set, asserts that substring in the body — so a
green test means the app served its own content, not a bare 200. `contains` is a
first-class server field (HealthcheckSection); the runtime readiness probe
enforces the same assertion.
"""

from __future__ import annotations

from pathlib import Path

from hop3_testing.catalog.loader import (
    _extract_healthcheck_from_hop3_toml,
    generate_test_definition_from_hop3_toml,
)


def test_extract_healthcheck_defaults():
    assert _extract_healthcheck_from_hop3_toml({}) == {"path": "/", "contains": None}


def test_extract_healthcheck_reads_path_and_contains():
    hc = _extract_healthcheck_from_hop3_toml({
        "healthcheck": {"path": "/h", "contains": "Hi"}
    })
    assert hc == {"path": "/h", "contains": "Hi"}


def test_default_validation_carries_healthcheck_contains():
    td = generate_test_definition_from_hop3_toml(
        Path("apps/real-apps-native/x"),
        {"metadata": {"id": "x"}, "healthcheck": {"path": "/h", "contains": "Hi"}},
    )
    http = [v for v in td.validations if v.type == "http"]
    assert len(http) == 1
    assert http[0].path == "/h"
    assert http[0].expect.contains == "Hi"


def test_default_validation_contains_none_without_healthcheck_contains():
    td = generate_test_definition_from_hop3_toml(
        Path("apps/real-apps-native/x"),
        {"metadata": {"id": "x"}, "healthcheck": {"path": "/h"}},
    )
    http = [v for v in td.validations if v.type == "http"]
    assert http[0].path == "/h"
    assert http[0].expect.contains is None


def test_explicit_test_validations_still_win():
    td = generate_test_definition_from_hop3_toml(
        Path("apps/real-apps-native/x"),
        {
            "metadata": {"id": "x"},
            "healthcheck": {"path": "/h", "contains": "from-healthcheck"},
            "test": {
                "validations": [{"path": "/api", "status": 200, "contains": "Hi"}]
            },
        },
    )
    http = [v for v in td.validations if v.type == "http"]
    # Explicit [[test.validations]] override the healthcheck-derived default.
    assert any(v.path == "/api" and v.expect.contains == "Hi" for v in http)
