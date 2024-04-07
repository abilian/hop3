from __future__ import annotations

from hop3.run.uwsgi import UwsgiSettings


def test_settings():
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
