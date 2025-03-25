from __future__ import annotations

import asyncio
import html
import shlex
import subprocess

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

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
    <input
        type="text" id="commandInput"
        onkeydown="if (event.keyCode == 13) sendCommand()">
    <button onclick="sendCommand()">Send</button>
    <div id="output" style="border: 1px solid black; height: 200px; overflow: auto; white-space: pre-wrap;"></div>
</body>
</html>
"""


def terminal_endpoint(request: Request):
    return HTMLResponse(TEMPLATE)


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            command = await websocket.receive_text()
            print(f"Received command: {command}")

            try:
                command_list = shlex.split(command)
                process = await asyncio.create_subprocess_exec(
                    *command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )

                async def send_output(stream, output_type):
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        await websocket.send_text(
                            f"{output_type}: {html.escape(line.decode())}"
                        )

                await asyncio.gather(
                    send_output(process.stdout, "stdout"),
                    send_output(process.stderr, "stderr"),
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
        Route("/terminal", endpoint=terminal_endpoint),
        WebSocketRoute("/terminal/ws", endpoint=websocket_endpoint),
    ]
