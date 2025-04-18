# Copyright (c) 2025, Abilian SAS

# ruff: noqa: G004, SIM105, TRY400
from __future__ import annotations

import asyncio
import html
import logging
from typing import TYPE_CHECKING

from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.websockets import WebSocket

    from hop3.server.asgi import SetupContext


# language=html
TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>WebSocket Shell</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <!-- Removed Socket.IO script -->
    <style>
        body { font-family: sans-serif; }
        #output {
            border: 1px solid black;
            height: 300px;
            overflow-y: scroll; /* Changed to scroll */
            white-space: pre-wrap;
            word-wrap: break-word; /* Added for long lines */
            margin-top: 10px;
            padding: 5px;
            background-color: #f8f8f8;
        }
        .stdout { color: black; }
        .stderr { color: red; }
        .error { color: orange; font-weight: bold; }
        .info { color: blue; }
    </style>

    <script>
        let socket;

        function connectWebSocket() {
            // Construct WebSocket URL dynamically
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/terminal/ws`;
            console.log(`Connecting to ${wsUrl}`);

            socket = new WebSocket(wsUrl);

            socket.onopen = function(event) {
                console.log('WebSocket connection opened!');
                addOutput('Connected to server.', 'info');
            };

            socket.onmessage = function(event) {
                console.log('Message from server:', event.data);
                try {
                    const msg = JSON.parse(event.data); // Expect JSON
                    if (msg.type && msg.data !== undefined) {
                         addOutput(msg.data, msg.type); // Use type as CSS class
                    } else {
                         addOutput(`Invalid message format: ${event.data}`, 'error');
                    }
                } catch (e) {
                    console.error("Failed to parse JSON:", e);
                    // Display raw data if JSON parsing fails
                    addOutput(`Raw data: ${event.data}`, 'info');
                }
            };

            socket.onerror = function(error) {
                console.error('WebSocket Error:', error);
                addOutput(`WebSocket Error: ${error.message || 'Connection failed'}`, 'error');
            };

            socket.onclose = function(event) {
                console.log('WebSocket connection closed:', event);
                addOutput(`Connection closed. Code: ${event.code}, Reason: ${event.reason || 'N/A'}`, 'info');
                // Optional: attempt to reconnect
                // setTimeout(connectWebSocket, 5000); // Reconnect after 5 seconds
            };
        }

        function addOutput(message, type = 'stdout') {
             // Sanitize message client-side as well for safety, though server escapes too
            const sanitizedMessage = message.replace(/</g, "<").replace(/>/g, ">");

            const outputDiv = document.getElementById('output');
            outputDiv.innerHTML += `<span class="${type}">${sanitizedMessage}</span><br>`;
            outputDiv.scrollTop = outputDiv.scrollHeight; // Scroll to bottom
        }

        function sendCommand() {
            if (!socket || socket.readyState !== WebSocket.OPEN) {
                addOutput('Not connected to server.', 'error');
                return;
            }
            const input = document.getElementById('commandInput');
            const command = commandInput.value;
            if (command.trim() === '') return; // Don't send empty commands

            console.log(`Sending command: ${command}`);
            socket.send(command); // Send raw command string
            commandInput.value = ''; // Clear input
        }

        // Add event listener after the DOM is loaded
        document.addEventListener('DOMContentLoaded', (event) => {
            // Re-fetch elements here to ensure they exist
            const input = document.getElementById('commandInput');
            const sendButton = document.getElementById('sendButton');

            input.addEventListener('keydown', function(event) {
                 if (event.key === 'Enter') { // Use event.key for modern browsers
                    sendCommand();
                 }
            });
            sendButton.addEventListener('click', sendCommand);

            connectWebSocket(); // Initialize WebSocket connection on load
        });

    </script>
</head>
<body>
    <h1>WebSocket Shell</h1>
    <input type="text" id="commandInput" placeholder="Enter command...">
    <button id="sendButton">Send</button>
    <hr>
    <p>Output:</p>
    <div id="output"></div>
</body>
</html>
"""


def terminal_endpoint(request: Request):
    # Ensure static dir exists if we were serving specific files from it,
    # but it's not strictly needed just for the template.
    # STATIC_DIR.mkdir(exist_ok=True)
    return HTMLResponse(TEMPLATE)


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info(f"WebSocket connection accepted from {websocket.client}")

    async def send_json(msg_type: str, data: str):
        """Helper to send structured JSON messages."""
        try:
            await websocket.send_json({"type": msg_type, "data": data})
        except Exception as e:
            logger.error(f"Failed to send message to client: {e}")

    try:
        while True:
            command = await websocket.receive_text()
            logger.info(f"Received command: {command}")

            if not command.strip():
                await send_json("info", "Received empty command.")
                continue  # Skip empty commands

            # TODO: later...
            # try:
            #     # SECURITY WARNING: Executes arbitrary commands!
            #     command_list = shlex.split(command)
            #     if not command_list:  # Should be caught by strip() check, but belts and suspenders
            #         await send_json("info", "Received empty command after parsing.")
            #         continue
            #
            #     process = await asyncio.create_subprocess_exec(
            #         *command_list,
            #         stdout=subprocess.PIPE,
            #         stderr=subprocess.PIPE,
            #         # Consider adding cwd= or env= for more control if needed
            #     )
            #     logger.info(f"Executing command: {command_list}")
            #
            #     # Use gather to concurrently read stdout and stderr
            #     stdout_task = asyncio.create_task(stream_output(process.stdout, websocket, "stdout"))
            #     stderr_task = asyncio.create_task(stream_output(process.stderr, websocket, "stderr"))
            #
            #     await asyncio.gather(stdout_task, stderr_task)
            #
            #     # Wait for the process to complete and get the return code
            #     return_code = await process.wait()
            #     logger.info(f"Command finished with return code: {return_code}")
            #     await send_json("info", f"Command finished with exit code {return_code}")
            #
            # except FileNotFoundError:
            #     logger.error(f"Command not found: {command_list[0]}")
            #     await send_json("error", f"Error: Command not found: '{html.escape(command_list[0])}'")
            # except PermissionError:
            #     logger.error(f"Permission denied for command: {command_list[0]}")
            #     await send_json("error", f"Error: Permission denied for command: '{html.escape(command_list[0])}'")
            # except Exception as e:
            #     logger.exception(f"Error executing command '{command}': {e}")  # Log full traceback
            #     await send_json("error", f"Error: {html.escape(str(e))}")

    except Exception as e:  # Catch disconnects and other errors
        logger.info(f"WebSocket connection closed or error: {e}")
    finally:
        # Ensure websocket is closed if not already
        try:
            await websocket.close()
        except RuntimeError:
            pass  # Already closed
        logger.info(f"WebSocket cleanup complete for {websocket.client}")


async def stream_output(
    stream: asyncio.StreamReader | None, websocket: WebSocket, output_type: str
):
    """Reads lines from a stream and sends them over WebSocket as JSON."""
    if stream is None:
        return
    while True:
        try:
            line_bytes = await stream.readline()
            if not line_bytes:
                break
            line_str = line_bytes.decode(errors="replace").rstrip()  # Decode safely
            await websocket.send_json({"type": output_type, "data": line_str})
        except Exception as e:
            logger.error(f"Error reading/sending {output_type}: {e}")
            try:
                # Try sending error details if possible
                await websocket.send_json({
                    "type": "error",
                    "data": f"Error streaming {output_type}: {html.escape(str(e))}",
                })
            except Exception:
                pass  # Ignore if sending also fails
            break  # Stop streaming this output type on error


def setup(ctx: SetupContext):
    ctx.routes.extend([
        Route("/terminal", endpoint=terminal_endpoint),
        # Mount("/terminal/static", app=StaticFiles(directory=STATIC_DIR, html=True)),
        WebSocketRoute("/terminal/ws", endpoint=websocket_endpoint),
    ])
