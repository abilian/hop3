# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import datetime as dt
from pathlib import Path

from starlette.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


class Templates(Jinja2Templates):
    def __init__(self):
        super().__init__(
            directory=TEMPLATE_DIR,
            # context_processors=[vite_app_context, app_context],
            auto_reload=True,
        )

        self.set_globals()
        self.set_filters()

    def set_globals(self):
        self.env.globals["now"] = dt.datetime.now
        # self.env.globals["config"] = config
        # Alias
        # self.env.globals["settings"] = config

    def set_filters(self):
        self.env.filters["dateformat"] = _dateformat

    def __call__(self, request, *args, **kwargs):
        return self.TemplateResponse(request, *args, **kwargs)


def _dateformat(value: dt.date | str) -> str:
    if isinstance(value, str):
        value = dt.date.fromisoformat(value)
    return value.strftime("%b %d, %Y")
