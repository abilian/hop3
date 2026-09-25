# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Shared streaming-deploy helper.

``deploy_app_streaming`` hands ``do_deploy`` to the build queue and streams its
logs over SSE, returning immediately with the stream response item. It is the
single implementation used by both ``hop3 deploy`` (DeployCmd) and
``hop3 catalog install`` (CatalogInstallCmd), and by the dashboard install form.

The queue (``deployers/build_queue.py``) is what bounds concurrent builds; this
module's job is to say, in the stream, when a deploy is waiting for a slot or
was refused a place in line.

Cross-thread contract: sessions are not thread-safe, so the background thread
opens its OWN session and re-fetches the app by primary key; it never receives
the request's Session or an attached App. Before handing over, the request
session is committed here. The request has usually just stopped the previous
instance, and the thread must start from that state: committed later, when the
request ends, it raced the build and could overwrite the state the deploy wrote.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hop3.deployers import do_deploy
from hop3.deployers.build_queue import BuildQueueFullError, get_build_queue
from hop3.lib import server_log
from hop3.orm import AppRepository, AppStateEnum, get_session_factory
from hop3.server.streaming import create_stream, stream_context

from ._errors import command_context
from ._response import stream

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App


def deploy_app_streaming(app: App, request_session: Session) -> dict:
    """
    Deploy ``app`` in a background thread with real-time SSE log streaming.

    Commits ``request_session``, then returns the single ``stream`` response item
    immediately; the caller wraps it in a list for the RPC result. The deploy's
    outcome (success or failure) is surfaced via the stream's terminal
    ``complete`` event — a failed deploy is never reported as success, and the
    operator alert in ``do_deploy`` (ADR 054) still fires.
    """
    app_name, app_id = app.name, app.id
    request_session.commit()
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
                record_deploy_failure(thread_session, app_id, e)
                log_stream.finish(success=False, error_message=str(e))

    build_queue = get_build_queue()
    try:
        ahead = build_queue.submit(run_deployment)
    except BuildQueueFullError as e:
        # Refused, and said so where the operator is already looking: the
        # stream they are about to connect to. `subscribe()` replays a
        # finished stream, so a client that connects late still gets this.
        log_stream.finish(success=False, error_message=str(e))
    else:
        if ahead >= build_queue.workers:
            log_stream.write(
                f"Waiting for a build slot: {build_queue.workers} builds are "
                f"running and {ahead - build_queue.workers} deploy(s) are ahead "
                f"of this one. It will start on its own.",
                fg="yellow",
            )

    # Return the stream_id immediately so the CLI can connect to the SSE endpoint.
    return stream(log_stream.stream_id)


def record_deploy_failure(
    db_session: Session, app_id: int, error: BaseException
) -> None:
    """
    Leave an app whose deploy raised in FAILED, with the reason, in the database.

    The reason is the underlying error: the one `command_context` wraps says
    only "deploying app failed" when the detail was already streamed.

    The deploy's own changes are rolled back, and with them any FAILED it set in
    memory, so without this the app kept whatever state was last committed:
    usually STARTING, which the next deploy then tripped over. By the time a
    deploy fails the previous instance has been stopped, so FAILED is the truth.
    Recording it must not mask the deploy's own error, which the caller reports.
    """
    try:
        db_session.rollback()
        app = AppRepository(session=db_session).get_one_or_none(id=app_id)
        if app is None or app.run_state == AppStateEnum.FAILED:
            return
        reason = str(error.__cause__ or error)
        app.transition_state(AppStateEnum.FAILED, reason[:1024])
        db_session.commit()
    except Exception:
        server_log.exception("could not record a failed deploy", app_id=app_id)
