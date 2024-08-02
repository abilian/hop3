# Copyright (c) 2023-2024, Abilian SAS

import contextlib
import json

from hop3_server.rpc.jsonrpc import Hop3Service
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


async def handle_rpc(request: Request):
    app = request.app
    service: Hop3Service = app.state.rpc_service
    json_request = await request.json()

    method = json_request["method"]
    assert method == "cli"

    params = json_request["params"][0]
    command = params[0]
    args = params[1:]

    try:
        result = service.call(command, args)
        result_rpc = {"jsonrpc": "2.0", "result": result, "id": 1}
        json_result = json.dumps(result_rpc)
        return Response(json_result, media_type="application/json")
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
    app.state.rpc_service = Hop3Service()
    yield
    print("Run on shutdown!")


app = Starlette(debug=True, routes=routes, lifespan=lifespan)
