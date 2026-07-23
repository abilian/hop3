# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Tests for validation `status_in` support (any-of status matching)."""

from __future__ import annotations

from hop3_testing.apps.deployment import _format_expected, _status_match
from hop3_testing.catalog.loader import _parse_validation


class TestStatusMatch:
    def test_int_equality(self):
        assert _status_match(200, 200)
        assert not _status_match(202, 200)

    def test_iterable_contains(self):
        assert _status_match(200, [200, 202])
        assert _status_match(202, [200, 202])
        assert not _status_match(500, [200, 202])

    def test_set_contains(self):
        assert _status_match(404, {200, 404, 503})
        assert not _status_match(200, {404, 503})

    def test_empty_iterable(self):
        assert not _status_match(200, [])


class TestFormatExpected:
    def test_int(self):
        assert _format_expected(200) == "200"

    def test_single_iterable(self):
        assert _format_expected([200]) == "200"

    def test_two_codes(self):
        assert _format_expected([200, 202]) == "200 or 202"
        # Order doesn't matter — sorted output.
        assert _format_expected([202, 200]) == "200 or 202"

    def test_three_or_more(self):
        assert _format_expected([200, 202, 503]) == "200, 202, or 503"

    def test_dedupes(self):
        assert _format_expected([200, 200, 202]) == "200 or 202"


class TestLoaderParsesStatusIn:
    def test_status_in_at_top_level(self):
        data = {"type": "http", "path": "/", "status_in": [200, 202]}
        v = _parse_validation(data)
        assert v.expect.status_in == [200, 202]

    def test_status_in_in_nested_expect(self):
        data = {
            "type": "http",
            "path": "/",
            "expect": {"status_in": [200, 202]},
        }
        v = _parse_validation(data)
        assert v.expect.status_in == [200, 202]

    def test_kebab_case_status_in(self):
        """TOML arrays sometimes use kebab-case; loader accepts both."""
        data = {"type": "http", "path": "/", "status-in": [200, 202]}
        v = _parse_validation(data)
        assert v.expect.status_in == [200, 202]

    def test_default_status_in_is_none(self):
        data = {"type": "http", "path": "/", "status": 200}
        v = _parse_validation(data)
        assert v.expect.status_in is None
        assert v.expect.status == 200

    def test_ints_coerced_from_toml_floats(self):
        """
        If TOML emits an array of ints as int types (expected),
        they survive. Testing defensive int() coercion.
        """
        data = {"type": "http", "status_in": [200, 202]}
        v = _parse_validation(data)
        status_in = v.expect.status_in
        assert status_in is not None
        assert status_in == [200, 202]
        assert all(isinstance(s, int) for s in status_in)
