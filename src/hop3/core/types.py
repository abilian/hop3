# TODO: duplicated

from __future__ import annotations

from typing import TypeAlias

Json: TypeAlias = dict[str, "Json"] | list["Json"] | str | int | float | bool | None
JsonDict: TypeAlias = dict[str, Json]
JsonList: TypeAlias = list[Json]
