from starlette.requests import Request

# language=html
TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>WebSocket Shell</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        var socket = io();

        socket.on('connect', function() {
            console.log('Connected!');
        });

        socket.on('output', function(msg) {
            var outputDiv = document.getElementById('output');
            outputDiv.innerHTML += msg.data + '<br>';
            outputDiv.scrollTop = outputDiv.scrollHeight; // Scroll to bottom
        });

        function sendCommand() {
            var command = document.getElementById('commandInput').value;
            socket.emit('command', {data: command});
            document.getElementById('commandInput').value = ''; // Clear input
        }
    </script>
</head>
<body>
    <h1>WebSocket Shell</h1>
    <input type="text" id="commandInput" onkeydown="if (event.keyCode == 13) sendCommand()">
    <button onclick="sendCommand()">Send</button>
    <div id="output" style="border: 1px solid black; height: 200px; overflow: auto; white-space: pre-wrap;"></div>
</body>
</html>
"""


async def handle_terminal(request: Request):
    json_request = await request.json()

    method = json_request["method"]
    assert method == "cli"

    params = json_request["params"][0]
    command = params[0]
    args = params[1:]

    try:
        result = call(command, args)
        result_rpc = {"jsonrpc": "2.0", "result": result, "id": 1}
        json_result = json.dumps(result_rpc)
        return Response(json_result, media_type="application/json")
    except ValueError as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


import asyncio
import subprocess
import html
import shlex
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute
from starlette.templating import Jinja2Templates
from starlette.websockets import WebSocket

templates = Jinja2Templates(directory="templates")


async def homepage(request):
    return templates.TemplateResponse("websocket_index.html", {"request": request})


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            command = await websocket.receive_text()
            print(f"Received command: {command}")

            try:
                command_list = shlex.split(command)
                process = await asyncio.create_subprocess_exec(
                    *command_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                async def send_output(stream, output_type):
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        await websocket.send_text(f"{output_type}: {html.escape(line.decode())}")

                await asyncio.gather(
                    send_output(process.stdout, "stdout"),
                    send_output(process.stderr, "stderr")
                )
                await process.wait()

            except Exception as e:
                await websocket.send_text(f"Error: {html.escape(str(e))}")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()


def setup(ctx):
    ctx.routes += [
        Route("/", endpoint=homepage),
        WebSocketRoute("/ws", endpoint=websocket_endpoint),
    ]
