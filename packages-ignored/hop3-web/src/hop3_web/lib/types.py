# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from typing import TypeAlias

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
