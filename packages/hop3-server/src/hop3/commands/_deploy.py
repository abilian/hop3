# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Shared streaming-deploy helper.

``deploy_app_streaming`` runs ``do_deploy`` in a daemon thread and streams its
logs over SSE, returning immediately with the stream response item. It is the
single implementation used by both ``hop3 deploy`` (DeployCmd) and
``hop3 catalog install`` (CatalogInstallCmd), and by the dashboard install form.

Cross-thread contract (why this takes an id, not an ORM object): the RPC request
session is committed and CLOSED the moment the command returns the stream item
(server/controllers/rpc.py). Sessions are not thread-safe, so the background
thread must open its OWN session and re-fetch the app by primary key — hence the
signature is ``(app_name, app_id)`` and never a Session or an attached App.
"""

from __future__ import annotations

import contextlib
import threading
from datetime import UTC, datetime

from hop3.deployers import do_deploy
from hop3.orm import AppRepository, get_session_factory
from hop3.server.streaming import create_stream, stream_context

from ._errors import command_context
from ._response import stream


def deploy_app_streaming(app_name: str, app_id: int) -> dict:
    """
    Deploy ``app_id`` in a background thread with real-time SSE log streaming.

    Returns the single ``stream`` response item immediately; the caller wraps it
    in a list for the RPC result. The deploy's outcome (success or failure) is
    surfaced via the stream's terminal ``complete`` event — a failed deploy is
    never reported as success, and the operator alert in ``do_deploy`` (ADR 054)
    still fires. The ``app`` row MUST already be committed before this is called,
    or the thread's fresh session will not see it.
    """
    log_stream = create_stream(app_name)

    def run_deployment() -> None:
        # A fresh session for this thread — the request session is already gone.
        session_factory = get_session_factory()
        with session_factory() as thread_session:
            try:
                app_repo = AppRepository(session=thread_session)
                thread_app = app_repo.get_one_or_none(id=app_id)
                if not thread_app:
                    msg = f"App with id {app_id} not found"
                    raise ValueError(msg)

                # Order matters: stream_context BEFORE command_context so the
                # error formatter knows the detail was already streamed live.
                with (
                    stream_context(log_stream),
                    command_context("deploying app", app_name=app_name),
                ):
                    do_deploy(thread_app, db_session=thread_session)
                    thread_app.last_deployed_at = datetime.now(UTC)
                    thread_session.commit()
                log_stream.finish(success=True)
            except Exception as e:
                with contextlib.suppress(Exception):
                    thread_session.rollback()
                log_stream.finish(success=False, error_message=str(e))

    thread = threading.Thread(target=run_deployment, daemon=True)
    thread.start()

    # Return the stream_id immediately so the CLI can connect to the SSE endpoint.
    return stream(log_stream.stream_id)
