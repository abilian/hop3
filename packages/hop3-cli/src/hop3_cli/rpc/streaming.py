# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""SSE client for streaming deployment logs.

This module provides a client for consuming Server-Sent Events (SSE) from
the Hop3 server's streaming endpoint. Used for real-time deployment log display.

Usage:
    stream_deployment_logs(
        base_url="http://localhost:8000",
        stream_id="abc123",
        printer=printer,
        token="jwt_token",
    )
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import requests

from hop3_cli.exceptions import DeploymentError

if TYPE_CHECKING:
    from hop3_cli.ui.rich_printer import RichPrinter


def stream_deployment_logs(
    base_url: str,
    stream_id: str,
    printer: RichPrinter,
    token: str | None = None,
    verify_ssl: bool = True,
) -> None:
    """Connect to SSE stream and display logs in real-time.

    Args:
        base_url: Base URL of the Hop3 server (e.g., "http://localhost:8000")
        stream_id: Unique identifier for the deployment stream
        printer: RichPrinter for displaying output
        token: Optional JWT token for authentication
        verify_ssl: Whether to verify SSL certificates

    Raises:
        DeploymentError: If the deployment fails or stream cannot be connected.
    """
    # Build stream URL
    stream_url = f"{base_url.rstrip('/')}/api/stream/{stream_id}"

    # Set up headers
    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        # Use streaming mode to receive SSE events
        with requests.get(
            stream_url,
            headers=headers,
            stream=True,
            timeout=None,  # No timeout for streaming
            verify=verify_ssl,
        ) as response:
            if response.status_code == 404:
                printer.print([
                    {
                        "t": "error",
                        "text": f"Stream '{stream_id}' not found. The deployment may have already completed.",
                    }
                ])
                msg = f"Stream '{stream_id}' not found"
                raise DeploymentError(msg)

            if response.status_code != 200:
                printer.print([
                    {
                        "t": "error",
                        "text": f"Failed to connect to stream: HTTP {response.status_code}",
                    }
                ])
                msg = f"Failed to connect to stream: HTTP {response.status_code}"
                raise DeploymentError(msg)

            _process_sse_stream(response, printer)

    except requests.exceptions.ConnectionError as e:
        printer.print([
            {
                "t": "error",
                "text": f"Connection error: {e}",
            }
        ])
        msg = f"Connection error: {e}"
        raise DeploymentError(msg) from e
    except KeyboardInterrupt:
        printer.print([
            {
                "t": "warning",
                "text": "\nStreaming interrupted. Deployment continues on server.",
            }
        ])
        # Don't raise - deployment is still running on server


def _process_sse_stream(response: requests.Response, printer: RichPrinter) -> None:
    """Process SSE stream and display logs.

    Args:
        response: Streaming HTTP response
        printer: RichPrinter for displaying output

    Raises:
        DeploymentError: If the deployment fails.
    """
    event_type = "log"  # Default event type

    for line in response.iter_lines(decode_unicode=True):
        if line is None:
            continue

        line = line.strip()

        # Empty line = end of event
        if not line:
            continue

        # Comment (keepalive)
        if line.startswith(":"):
            continue

        # Event type
        if line.startswith("event:"):
            event_type = line[6:].strip()
            continue

        # Data
        if line.startswith("data:"):
            data_str = line[5:].strip()
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                # Plain text data
                printer.print([{"t": "text", "text": data_str}])
                continue

            if event_type == "log":
                # Display log entry
                printer.print([
                    {
                        "t": "log",
                        "msg": data.get("msg", ""),
                        "level": data.get("level", 0),
                        "fg": data.get("fg", ""),
                    }
                ])

            elif event_type == "complete":
                # Deployment completed
                success = data.get("success", False)
                error = data.get("error", "")
                duration = data.get("duration", 0)

                if success:
                    printer.print([
                        {
                            "t": "success",
                            "text": f"Deployment completed successfully in {duration:.1f}s",
                        }
                    ])
                    return
                printer.print([
                    {
                        "t": "error",
                        "text": error or "Deployment failed",
                    }
                ])
                raise DeploymentError(error or "Deployment failed")

    # Stream ended without completion event
    printer.print([
        {
            "t": "warning",
            "text": "Stream ended unexpectedly. Check server logs.",
        }
    ])
    msg = "Stream ended unexpectedly"
    raise DeploymentError(msg)


def check_streaming_support(base_url: str, token: str | None = None) -> bool:
    """Check if the server supports streaming.

    Args:
        base_url: Base URL of the Hop3 server
        token: Optional JWT token

    Returns:
        True if server supports /api/stream endpoint
    """
    # Try to access the stream endpoint (will 404 with no stream_id)
    # but at least we know the route exists
    try:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.get(
            f"{base_url.rstrip('/')}/api/stream/test",
            headers=headers,
            timeout=5,
        )
        # 404 means endpoint exists but stream not found (expected)
        # 405 or other errors mean endpoint doesn't exist
        return response.status_code in {200, 404}
    except Exception:
        return False
