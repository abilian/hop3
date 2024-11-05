# Copyright (c) 2024, Abilian SAS

# ruff: noqa: PLR2004
from __future__ import annotations

from pathlib import Path

from devtools import debug
from hop3.core.env import Env


def test_initialization() -> None:
    env = Env({"key1": "value1", "key2": 2})
    assert env["key1"] == "value1"
    assert env["key2"] == "2"


def test_set_item() -> None:
    env = Env()
    env["key"] = "value"
    assert env["key"] == "value"


def test_get_item() -> None:
    env = Env({"key": "value"})
    debug(env.data)
    assert env["key"] == "value"


def test_del_item() -> None:
    env = Env({"key": "value"})
    del env["key"]
    assert "key" not in env


def test_contains() -> None:
    env = Env({"key": "value"})
    assert "key" in env
    assert "nonexistent" not in env


def test_len() -> None:
    env = Env({"key1": "value1", "key2": "value2"})
    assert len(env) == 2


def test_iter() -> None:
    env = Env({"key1": "value1", "key2": "value2"})
    keys = list(iter(env))
    assert "key1" in keys
    assert "key2" in keys


def test_copy() -> None:
    env = Env({"key": "value"})
    env_copy = env.copy()
    assert env_copy["key"] == "value"
    env_copy["key"] = "new_value"
    assert env["key"] != env_copy["key"]


def test_update() -> None:
    env = Env({"key1": "value1"})
    env.update({"key2": "value2"})
    assert env["key2"] == "value2"


def test_get() -> None:
    env = Env({"key": "value"})
    assert env.get("key") == "value"
    assert env.get("nonexistent", "default") == "default"


def test_get_int() -> None:
    env = Env({"key": "1"})
    assert env.get_int("key") == 1
    assert env.get_int("nonexistent", 2) == 2


def test_get_bool() -> None:
    env = Env({"key": "true"})
    assert env.get_bool("key") is True
    assert env.get_bool("nonexistent") is False


def test_get_path() -> None:
    env = Env({"key": "/some/path"})
    assert env.get_path("key") == Path("/some/path")
    assert env.get_path("nonexistent", "/default/path") == Path("/default/path")


def test_parse_settings(tmp_path) -> None:
    env = Env()
    env_file = tmp_path / "test.env"
    env_file.write_text("key=value\n")
    env.parse_settings(env_file)
    assert env["key"] == "value"
