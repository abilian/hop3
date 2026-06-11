# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from hop3.run.uwsgi.settings import UwsgiSettings


def test_settings() -> None:
    settings = UwsgiSettings()
    settings.add("module", "command")
    settings.add("threads", "4")
    settings += [
        ("plugin", "python3"),
    ]
    assert settings.values == [
        ("module", "command"),
        ("threads", "4"),
        ("plugin", "python3"),
    ]


def test_add_coerces_value_to_string() -> None:
    """add() stores any value as its str() form (ini values are always text)."""
    settings = UwsgiSettings()
    settings.add("processes", 4)
    settings.add("enabled", True)

    assert settings.values == [("processes", "4"), ("enabled", "True")]


def test_add_keeps_duplicate_keys() -> None:
    """Duplicate keys are preserved as separate entries (uWSGI allows repeats)."""
    settings = UwsgiSettings()
    settings.add("plugin", "jvm")
    settings.add("plugin", "jwsgi")

    assert settings.values == [("plugin", "jvm"), ("plugin", "jwsgi")]


def test_append_unpacks_key_value_pair() -> None:
    """append() takes a (key, value) tuple and stores it as one entry."""
    settings = UwsgiSettings()
    settings.append(("module", "app:application"))

    assert settings.values == [("module", "app:application")]


def test_extend_preserves_insertion_order() -> None:
    """extend() adds every pair in the iterable, left to right."""
    settings = UwsgiSettings()
    settings.extend([("a", "1"), ("b", "2"), ("c", "3")])

    assert settings.values == [("a", "1"), ("b", "2"), ("c", "3")]


def test_write_emits_uwsgi_header_and_sorts_keys(tmp_path) -> None:
    """write() produces an [uwsgi] section with key = value lines sorted by key."""
    settings = UwsgiSettings()
    settings.add("processes", 1)
    settings.add("master", "true")
    settings.add("chdir", "/srv/app")

    target = tmp_path / "worker.ini"
    settings.write(target)

    assert target.read_text() == (
        "[uwsgi]\nchdir = /srv/app\nmaster = true\nprocesses = 1\n"
    )


def test_write_groups_duplicate_keys_after_sort(tmp_path) -> None:
    """Sorting is stable per (key, value), so repeated keys land together."""
    settings = UwsgiSettings()
    settings.add("plugin", "rack")
    settings.add("module", "config.ru")
    settings.add("plugin", "rbrequire")

    target = tmp_path / "worker.ini"
    settings.write(target)

    assert target.read_text() == (
        "[uwsgi]\nmodule = config.ru\nplugin = rack\nplugin = rbrequire\n"
    )


def test_write_empty_settings_emits_only_header(tmp_path) -> None:
    """An empty settings bag still writes a valid (header-only) ini file."""
    target = tmp_path / "empty.ini"
    UwsgiSettings().write(target)

    assert target.read_text() == "[uwsgi]\n"


def test_instances_do_not_share_default_values_list() -> None:
    """Each UwsgiSettings gets its own list (default_factory, not shared mutable)."""
    a = UwsgiSettings()
    b = UwsgiSettings()
    a.add("x", "1")

    assert a.values == [("x", "1")]
    assert b.values == []
