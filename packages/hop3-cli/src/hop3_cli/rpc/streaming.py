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

# Connect timeout: how long to wait for the initial TCP/TLS handshake.
# Tight bound — if the server isn't reachable in 30s it likely never will be.
_STREAM_CONNECT_TIMEOUT_SECONDS = 30.0

# Read timeout: max gap between successive bytes once the stream is open.
# The server emits SSE keepalive comments every ~15s, so any gap longer
# than this means the connection has stalled (slowloris-style or a hung
# server). Generous default so legitimate long deploys aren't cut off,
# but bounded so a CI runner can never wait forever.
_STREAM_READ_TIMEOUT_SECONDS = 300.0


def stream_deployment_logs(
    base_url: str,
    stream_id: str,
    printer: RichPrinter,
    token: str | None = None,
    verify_ssl: bool | str = True,
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
        # Use streaming mode to receive SSE events.
        # SECURITY: bound both connect and read timeouts. ``timeout=None``
        # would let a slowloris-style hang or a stuck server keep a CI
        # runner blocked indefinitely. The read timeout is the inter-byte
        # gap, which is well-defined for SSE because the server emits
        # keepalive comments — so a missed keepalive trips it cleanly.
        with requests.get(
            stream_url,
            headers=headers,
            stream=True,
            timeout=(_STREAM_CONNECT_TIMEOUT_SECONDS, _STREAM_READ_TIMEOUT_SECONDS),
            verify=verify_ssl,
            # Do NOT follow redirects. The stream endpoint requires auth;
            # when the token is missing/rejected it answers 3xx → /auth/login.
            # If we followed it, requests would fetch the HTML login page,
            # see a 200, hand non-SSE HTML to the parser, and the loop would
            # end with no `complete` event — surfacing the real deployment
            # error as a useless "Stream ended unexpectedly". Treating the
            # 3xx as a hard auth failure keeps the actual cause visible.
            allow_redirects=False,
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

            if response.is_redirect or response.status_code in {
                301,
                302,
                303,
                307,
                308,
            }:
                location = response.headers.get("Location", "(unknown)")
                printer.print([
                    {
                        "t": "error",
                        "text": (
                            f"Stream authentication failed: the server redirected "
                            f"(HTTP {response.status_code} → {location}) instead of "
                            f"streaming. The deployment ran but its progress/errors "
                            f"could not be read. Check 'journalctl -u hop3-server' on "
                            f"the server for the real cause."
                        ),
                    }
                ])
                msg = (
                    f"Stream authentication failed (HTTP {response.status_code} "
                    f"redirect to {location})"
                )
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

    except requests.exceptions.ConnectTimeout as e:
        msg = (
            f"Timed out connecting to {stream_url} after "
            f"{_STREAM_CONNECT_TIMEOUT_SECONDS:.0f}s. The server is "
            "unreachable; the deployment may still be running."
        )
        printer.print([{"t": "error", "text": msg}])
        raise DeploymentError(msg) from e
    except requests.exceptions.ReadTimeout as e:
        msg = (
            f"Stream stalled (no data for "
            f"{_STREAM_READ_TIMEOUT_SECONDS:.0f}s). The deployment "
            "may still be running on the server."
        )
        printer.print([{"t": "error", "text": msg}])
        raise DeploymentError(msg) from e
    except requests.exceptions.ConnectionError as e:
        printer.print([
            {
                "t": "error",
                "text": f"Connection error: {e}",
            }
        ])
        msg = f"Connection error: {e}"
        raise DeploymentError(msg) from e
    except (requests.exceptions.RequestException, OSError) as e:
        # TLS/CA misconfiguration surfaces here: an SSLError (e.g. a pinned
        # ssl_cert that doesn't match), or an OSError when requests is handed a
        # bogus CA-bundle path (the old `verify="false"` string bug). Without
        # this, such errors escaped as a raw exception that bypassed the
        # caller's DeploymentError handler and reported an opaque GENERAL_ERROR
        # on a deploy that actually ran (audit 2026-06 B1).
        msg = f"Stream connection failed (TLS/transport): {e}"
        printer.print([{"t": "error", "text": msg}])
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
                    # "deployed successfully" mirrors the non-streaming deploy
                    # response (commands/app.py) so scripts and docs can assert
                    # one consistent success phrase regardless of streaming.
                    printer.print([
                        {
                            "t": "success",
                            "text": f"App deployed successfully in {duration:.1f}s",
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
