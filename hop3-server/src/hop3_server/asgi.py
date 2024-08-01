# Copyright (c) 2023-2024, Abilian SAS

import contextlib

from hop3_server.rpc.jsonrpc import Hop3Service
from jsonrpcserver import dispatch
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


async def handle_rpc(request: Request):
    try:
        body = await request.body()
        result = dispatch(body)
        return Response(result, media_type="application/json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def handle_home(request: Request):  # noqa: RUF029
    return JSONResponse({"message": "Hello, world!"})


routes = [
    Route("/", handle_home),
    Route("/rpc", handle_rpc, methods=["POST"]),
]


@contextlib.asynccontextmanager
async def lifespan(app):  # noqa: RUF029
    print("Run at startup!")
    app.state = Hop3Service()
    yield
    print("Run on shutdown!")


app = Starlette(debug=True, routes=routes, lifespan=lifespan)
