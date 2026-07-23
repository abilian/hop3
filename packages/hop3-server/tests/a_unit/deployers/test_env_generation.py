# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The CSPRNG secret generator for [env] { generate = ... } (ADR 046).

`generate_secret_value` is the pure, functional core: a generate spec in, a
value out, backed by the stdlib `secrets` module (never `random`).
"""

from __future__ import annotations

import base64
import uuid

import pytest

from hop3.deployers.env_provisioning import generate_secret_value


def test_hex_length_is_two_chars_per_byte():
    v = generate_secret_value({"generate": "hex", "length": 16})
    assert len(v) == 32
    int(v, 16)  # parses as hex


def test_base64_decodes_to_requested_bytes():
    v = generate_secret_value({"generate": "base64", "length": 32})
    assert len(base64.b64decode(v)) == 32


def test_urlsafe_is_non_empty():
    assert generate_secret_value({"generate": "urlsafe", "length": 24})


def test_password_length_and_alphabet():
    v = generate_secret_value({"generate": "password", "length": 24})
    assert len(v) == 24
    assert v.isalnum()


def test_uuid_is_a_uuid_and_ignores_length():
    v = generate_secret_value({"generate": "uuid", "length": 999})
    assert uuid.UUID(v)


def test_prefix_is_prepended():
    v = generate_secret_value({"generate": "base64", "length": 32, "prefix": "base64:"})
    assert v.startswith("base64:")
    assert len(base64.b64decode(v.removeprefix("base64:"))) == 32


def test_defaults_when_length_omitted():
    assert len(generate_secret_value({"generate": "hex"})) == 64  # 32 bytes
    assert len(generate_secret_value({"generate": "password"})) == 24


def test_values_are_unique_across_calls():
    a = generate_secret_value({"generate": "hex"})
    b = generate_secret_value({"generate": "hex"})
    assert a != b


def test_unknown_generator_raises():
    with pytest.raises(ValueError, match="Unknown"):
        generate_secret_value({"generate": "md5"})
