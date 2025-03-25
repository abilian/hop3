# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from starlette.applications import Starlette

from hop3.routes import routes

# DEBUG = bool(os.environ.get("HOP3_DEBUG", False))
DEBUG = True


app = Starlette(debug=DEBUG, routes=routes)
