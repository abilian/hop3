# Copyright (c) 2023-2024, Abilian SAS

"""Custom types for CLI parameters."""

from __future__ import annotations

from click import Context, Parameter, ParamType

from hop3.core.app import App, get_app


class AppParamType(ParamType):
    name = "app"

    def convert(self, value: str, param: Parameter | None, ctx: Context | None) -> App:
        app_obj = get_app(value)
        return app_obj

    def __repr__(self) -> str:
        return "APP"
