# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Server-wide [limits] policy on HopConfig (ADR 046 §3 / P2.2)."""

from __future__ import annotations

from typing import Any

from hop3.config import HopConfig


class _FakeLoader:
    """Minimal ConfigLoader stub returning typed values from a dict."""

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def get_str(self, key: str, default: Any = "") -> Any:
        return self.values.get(key, default)

    def get_bool(self, key: str, default: Any = False) -> Any:
        return self.values.get(key, default)

    def get_int(self, key: str, default: Any = 0) -> Any:
        return self.values.get(key, default)

    def get_float(self, key: str, default: Any = 0.0) -> Any:
        return self.values.get(key, default)


def _config(**values: Any) -> HopConfig:
    return HopConfig(config_loader=_FakeLoader(values))


def test_limits_default_off_for_single_tenant_boxes():
    cfg = _config()
    assert cfg.LIMITS_STRICT is True  # safe posture by default
    assert cfg.limits_defaults() == {}  # no server-imposed caps
    assert cfg.limits_ceilings() == {}


def test_limits_defaults_only_include_set_dimensions():
    cfg = _config(LIMITS_DEFAULT_MEMORY="512M", LIMITS_DEFAULT_CPU=1.0)
    assert cfg.limits_defaults() == {"memory": "512M", "cpu": 1.0}
    # processes left at 0 → omitted, not a 0-process cap.
    assert "processes" not in cfg.limits_defaults()


def test_limits_ceilings_assembled():
    cfg = _config(
        LIMITS_CEILING_MEMORY="2G",
        LIMITS_CEILING_CPU=4.0,
        LIMITS_CEILING_PROCESSES=1024,
    )
    assert cfg.limits_ceilings() == {
        "memory": "2G",
        "cpu": 4.0,
        "processes": 1024,
    }


def test_limits_strict_can_be_disabled_for_best_effort():
    assert _config(LIMITS_STRICT=False).LIMITS_STRICT is False
