# Copyright (c) 2023-2024, Abilian SAS

from hop3_server.routes import routes
from starlette.applications import Starlette

# DEBUG = bool(os.environ.get("HOP3_DEBUG", False))
DEBUG = True


app = Starlette(debug=DEBUG, routes=routes)
