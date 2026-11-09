# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""JSON-RPC controller for Hop3 CLI commands."""

from __future__ import annotations

import contextlib
import json
import time
import traceback
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import anyio
import anyio.to_thread
from advanced_alchemy.exceptions import RepositoryError
from litestar import Controller, Request, post
from litestar.response import Response

from hop3 import config
from hop3.commands import Command
from hop3.commands._errors import CommandFailedError
from hop3.core.plugins import get_plugin_manager
from hop3.core.roles import Role
from hop3.di.providers import REPOSITORY_TYPES
from hop3.lib import Abort, format_diagnosis
from hop3.lib.console import verbosity_context
from hop3.lib.logging import server_log
from hop3.lib.registry import lookup
from hop3.lib.repository_errors import (
    repository_error_diagnosis as _repository_error_diagnosis,
)
from hop3.lib.scanner import scan_package
from hop3.lib.suggestions import (
    DidYouMeanError,
    SuggestionKind,
    closest_matches,
)
from hop3.orm import get_session_factory
from hop3.server.security.authorization import lookup_account
from hop3.server.security.proxy_headers import client_ip
from hop3.server.security.rate_limit import AUTH_RATE_LIMITER, RateLimitError
from hop3.server.security.web_auth import current_identity

# JSON-RPC application error codes. The spec reserves -32000..-32099 for
# implementation-defined errors; HTTP status codes (401/429) are a different
# namespace and were being sent in this field.
RPC_ERROR_INVALID_REQUEST = -32600
RPC_ERROR_METHOD_NOT_FOUND = -32601
RPC_ERROR_INVALID_PARAMS = -32602
RPC_ERROR_UNAUTHENTICATED = -32001
RPC_ERROR_RATE_LIMITED = -32002
# Signed in, but the account's role is below the command's (ADR 061). Distinct
# from -32001 so a client can tell "sign in" from "ask an admin".
RPC_ERROR_FORBIDDEN = -32003

# ADR 042, rule D: the context sources the CLI reports that name the server
# explicitly (`--context`, `HOP3_CONTEXT`, `HOP3_API_URL`); the others are a
# checkout's binding and the global current context.
EXPLICIT_CONTEXT_SOURCES = frozenset({"flag", "env", "env_url"})
#: ``error.data.kind`` of a change refused because nothing named the server.
PROTECTED_NEEDS_EXPLICIT = "protected_needs_explicit_target"
#: ``error.data.kind`` of a change that waits for the typed confirmation.
PROTECTED_NEEDS_CONFIRMATION = "protected_needs_confirmation"
RPC_ERROR_INTERNAL = -32603
#: Another command holds the one command slot past the wait below.
RPC_ERROR_SERVER_BUSY = -32004

#: Version of the /rpc contract (envelope, params, error ``data``). Reported on
#: every response in the `PROTOCOL_HEADER` header; a client that sends
#: ``params.protocol`` is refused loudly when it differs. Bump it on a change a
#: client of the previous version would misread.
RPC_PROTOCOL_VERSION = 1
PROTOCOL_HEADER = "Hop3-RPC-Protocol"

#: How long a call waits for the command slot before answering "server busy".
COMMAND_SLOT_WAIT_SECONDS = 30.0

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

    from sqlalchemy.orm import Session

    from hop3.lib.types import Json, JsonDict


class ServerBusyError(Exception):
    """The command slot stayed taken for the whole wait."""

    def __init__(self, holder: str | None, held_for: float | None) -> None:
        #: None between one command's release and the next one's start: the
        #: slot is taken but its holder is not named yet, so no duration.
        self.holder = holder
        self.held_for: int | None = None if held_for is None else round(held_for)
        super().__init__(f"server busy: {self.running}")

    @property
    def running(self) -> str:
        """What holds the slot, in the words the refusal uses."""
        if self.holder and self.held_for is not None:
            return f"'hop3 {self.holder}' has been running for {self.held_for}s"
        return "another command is running"


class CommandSlot:
    """
    One command at a time, with a bounded wait and the holder's name.

    Commands run one at a time (see the note at the call site in handle_rpc).
    An unbounded wait made a long backup look like a hung server to every
    other caller, `hop3 login` included; a caller now waits at most
    ``wait_seconds`` and is told which command holds the slot.
    """

    def __init__(self, wait_seconds: float) -> None:
        self.wait_seconds = wait_seconds
        self._semaphore = anyio.Semaphore(1)
        # One tuple, set and cleared together, so a reader never pairs one
        # command's name with another's start time.
        self._held: tuple[str | None, float | None] = (None, None)

    @asynccontextmanager
    async def hold(self, display_name: str) -> AsyncGenerator[None, None]:
        """Hold the slot for ``display_name``, or raise `ServerBusyError`."""
        acquired = False
        with anyio.move_on_after(self.wait_seconds):
            await self._semaphore.acquire()
            acquired = True
        if not acquired:
            holder, since = self._held
            raise ServerBusyError(
                holder, None if since is None else time.monotonic() - since
            )
        self._held = (display_name, time.monotonic())
        try:
            yield
        finally:
            self._held = (None, None)
            self._semaphore.release()

    @property
    def holder(self) -> str | None:
        """The command holding the slot, if one has been named."""
        return self._held[0]


_COMMAND_SLOT = CommandSlot(COMMAND_SLOT_WAIT_SECONDS)
_PROTOCOL_HEADERS = {PROTOCOL_HEADER: str(RPC_PROTOCOL_VERSION)}

# Scan and register all CLI commands (including aliases)
scan_package("hop3.commands")


def register_command(
    table: dict[tuple[str, ...], type[Command]], cmd: type[Command]
) -> None:
    """
    Add ``cmd`` under its name and aliases, refusing a name already taken.

    A silent overwrite let the later of two commands (a plugin's, say) take a
    name or alias from the earlier one, depending on import order.
    """
    # ADR 036 D1/D18: names and aliases are tuples of tokens.
    for key in (cmd.name, *cmd.aliases):
        taken = table.get(key)
        if taken is not None and taken is not cmd:
            msg = (
                f"Command name 'hop3 {format_command_name(key)}' is claimed by "
                f"both {taken.__module__}.{taken.__qualname__} and "
                f"{cmd.__module__}.{cmd.__qualname__}; rename one or drop the alias."
            )
            raise RuntimeError(msg)
        table[key] = cmd


def build_command_table(
    command_classes: Iterable[type[Command]],
) -> dict[tuple[str, ...], type[Command]]:
    """A dispatch table for ``command_classes``; raises on a name collision."""
    table: dict[tuple[str, ...], type[Command]] = {}
    for command in command_classes:
        register_command(table, command)
    return table


def _build_command_table() -> dict[tuple[str, ...], type[Command]]:
    """
    Build the RPC dispatch table from core + plugin-contributed commands.

    Core commands live in `hop3.commands` (scanned above and found via the
    registry). Plugins contribute additional commands through the
    `cli_commands()` hook — e.g. the addon plugins add `addon <type> <verb>`
    commands such as `addon postgres credentials`. Calling the hook also
    forces plugin loading, so this works regardless of import order.
    """
    contributed = get_plugin_manager().hook.cli_commands()
    plugin_commands = [cmd for group in contributed for cmd in group]
    return build_command_table([*lookup(Command), *plugin_commands])


_commands: dict[tuple[str, ...], type[Command]] = _build_command_table()
commands = _commands

# Maximum command-name depth we're willing to match. Per ADR 036 D3/D12,
# 3 levels is the strong guideline; we allow up to 4 to leave headroom for
# unusual plugin-contributed commands without forcing a hard rejection.
_MAX_COMMAND_DEPTH = 4


def find_command(cli_args: list[str]) -> tuple[type[Command] | None, int]:
    """
    Find the command matching the longest tuple prefix of cli_args.

    Tries longest prefix first: for cli_args = ["addon", "postgres", "diagnose", "mydb"],
    checks ("addon", "postgres", "diagnose", "mydb") → ("addon", "postgres", "diagnose")
    → ("addon", "postgres") → ("addon",). Returns the command class for the first
    match found, plus the number of tokens consumed.

    Returns (None, 0) if nothing matches.
    """
    for n in range(min(len(cli_args), _MAX_COMMAND_DEPTH), 0, -1):
        key = tuple(cli_args[:n])
        if key in _commands:
            return _commands[key], n
    return None, 0


def typed_command_name(cli_args: list[str]) -> tuple[str, ...]:
    """
    Name the command the operator meant, for an unknown-command failure.

    Walks the registry's prefix tree as far as it goes, then adds the token
    that broke the walk: `admin set-password` is reported in full instead of
    just `admin`, so the suggestion is drawn against what was actually typed
    (`user set-password`) rather than against every command starting with a
    similar first word (`domain`, `addon`). Tokens past the break are the
    command's arguments and stay out of the name.
    """
    prefixes = {name[:n] for name in commands for n in range(1, len(name))}
    depth = 0
    limit = min(len(cli_args), _MAX_COMMAND_DEPTH)
    while depth < limit and tuple(cli_args[: depth + 1]) in prefixes:
        depth += 1
    return tuple(cli_args[: depth + 1])


def _unknown_command_error(message: str, display_name: str) -> DidYouMeanError:
    """Attach the closest registered command names to an unknown-command error."""
    known = [format_command_name(name) for name in commands]
    return DidYouMeanError(
        message,
        kind=SuggestionKind.UNKNOWN_COMMAND,
        typed=display_name,
        candidates=closest_matches(display_name, known),
    )


def format_command_name(name: tuple[str, ...]) -> str:
    """Format a command name tuple for human display (e.g., in error messages)."""
    return " ".join(name)


def requires_authentication(command_class: type[Command]) -> bool:
    """
    Check if a command requires authentication.

    Uses the declarative `requires_auth` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if authentication is required, False otherwise
    """
    return command_class.requires_auth


def is_rate_limited(command_class: type[Command]) -> bool:
    """
    Check if a command must be throttled per client IP before dispatch.

    Uses the declarative `rate_limited` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if the command is rate limited, False otherwise
    """
    return command_class.rate_limited


def command_needs_username(command_class: type[Command]) -> bool:
    """
    Check if a command needs the authenticated username.

    Uses the declarative `pass_username` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if the command needs the username, False otherwise
    """
    return command_class.pass_username


def command_needs_token_info(command_class: type[Command]) -> bool:
    """
    Check if a command needs the full token information.

    Uses the declarative `pass_token_info` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if the command needs token info (jti, exp), False otherwise
    """
    return command_class.pass_token_info


def _injected_args(command_class: type, db_session: Session, display_name: str) -> dict:
    """Build the command's constructor arguments: session and/or repositories."""
    annotations = command_class.__annotations__
    class_args: dict = {}

    # Inject db_session if needed (legacy pattern)
    if "db_session" in annotations:
        class_args["db_session"] = db_session
        server_log.debug("Command uses db_session", command=display_name)

    # Inject repositories if needed (new pattern)
    for attr_name, repo_class in REPOSITORY_TYPES.items():
        if attr_name in annotations:
            class_args[attr_name] = repo_class(session=db_session)
            server_log.debug(
                f"Command uses {attr_name}",
                command=display_name,
                repo_type=repo_class.__name__,
            )
    return class_args


def call(
    command_name: tuple[str, ...], args: list[str], extra_args: JsonDict
) -> list[dict]:
    """
    Execute a CLI command with given arguments.

    Args:
        command_name: Tuple of tokens naming the command (e.g., ("config", "set"))
        args: Positional arguments for the command (tokens after the command name)
        extra_args: Keyword arguments for the command (verbosity is extracted as context)

    Returns:
        Command execution result

    Raises:
        DidYouMeanError: If the command is not found
        Exception: Whatever the command raised, unchanged, after a rollback;
            `RPCController._execute_command` maps each kind to its error code
    """
    display_name = format_command_name(command_name)
    command_class = commands.get(command_name)
    if command_class is None:
        msg = f"Command '{display_name}' not found"
        server_log.error("Command not found", command=display_name)
        raise _unknown_command_error(msg, display_name)

    server_log.debug(
        "Creating command instance",
        command=display_name,
        command_class=command_class.__name__,
    )

    # Extract verbosity from extra_args - it's a context parameter, not a command kwarg
    verbosity_val = extra_args.pop("verbosity", 1)
    verbosity = verbosity_val if isinstance(verbosity_val, int) else 1

    # Prepare command kwargs (without verbosity - it's handled via context)
    command_kwargs = extra_args.copy()

    session_factory = get_session_factory()
    db_session = session_factory()
    try:
        class_args = _injected_args(command_class, db_session, display_name)
        command = command_class(**class_args)

        try:
            server_log.debug(
                "Calling command.call()",
                command=display_name,
                args=args,
                extra_args_keys=list(command_kwargs.keys()),
                verbosity=verbosity,
            )
            # Set verbosity context for the duration of command execution
            with verbosity_context(verbosity):
                result = command.call(*args, **command_kwargs)
            server_log.debug(
                "Command.call() returned",
                command=display_name,
                result_type=type(result).__name__,
            )
            # Commit any pending changes (if not already committed by command)
            db_session.commit()
        except Exception as e:
            # Roll back, then re-raise unchanged: the exception's type is what
            # picks the JSON-RPC code (-32602 bad params, -32603 a failure while
            # running) and a RepositoryError's cause is its Diagnosis. Wrapping
            # everything in ValueError answered -32602 for a full disk.
            with contextlib.suppress(Exception):
                db_session.rollback()
            server_log.error(
                "Command.call() raised exception",
                command=display_name,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

        return result
    finally:
        # Always close the session, but handle any state errors gracefully
        try:
            db_session.close()
        except Exception as e:
            server_log.warning(
                "Error closing database session",
                command=display_name,
                error=str(e),
            )


class RPCController(Controller):
    """
    JSON-RPC endpoint controller for CLI commands.

    Handles JSON-RPC requests from the Hop3 CLI, executing commands
    on the server with authentication and authorization checks.
    """

    path = "/rpc"

    @post("/", status_code=200)
    async def handle_rpc(self, request: Request, data: dict) -> Response:
        """
        Handle JSON-RPC request.

        Args:
            request: HTTP request
            data: JSON-RPC request data from body

        Returns:
            JSON-RPC response
        """
        # Validate the envelope before touching it. Every member below used to
        # be read unguarded, so a malformed body raised KeyError/TypeError and
        # Litestar answered with an HTML 500 — not a JSON-RPC error object a
        # client can parse. The method check was an `assert`, which vanishes
        # under `python -O` and otherwise 500s instead of returning -32601.
        request_id = data.get("id") if isinstance(data, dict) else None

        if invalid := self._validate_envelope(data, request_id):
            return invalid

        params = data["params"]
        cli_args = params["cli_args"]
        extra_args: JsonDict = params.get("extra_args") or {}

        # Find the command by longest-prefix match (ADR 036 D1/D18).
        # For `hop3 config set FOO=bar`, cli_args = ["config", "set", "FOO=bar"];
        # the command name is the tuple ("config", "set") and args is ["FOO=bar"].
        command_class, n_consumed = find_command(cli_args)
        if command_class is None:
            command_name = typed_command_name(cli_args)
            args = cli_args[len(command_name) :]
        else:
            command_name = command_class.name
            args = cli_args[n_consumed:]
        display_name = format_command_name(command_name)

        # Log all incoming RPC commands for debugging
        server_log.info(
            "RPC request received",
            command=display_name,
            args=args,
            extra_args_keys=list(extra_args.keys()),
            request_id=request_id,
        )

        # Authenticate (before revealing whether the command exists) and
        # authorize, off the event loop: validating the token reads the
        # revocation list and authorizing reads the account, both database
        # reads. The identity is resolved once and reused below.
        refusal, identity = await anyio.to_thread.run_sync(
            self._authenticate_and_authorize,
            request,
            command_class,
            display_name,
            request_id,
        )
        if refusal:
            return refusal

        # Throttle credential-verifying commands (see Command.rate_limited)
        rate_error = self._check_rate_limit(request, command_class, request_id)
        if rate_error:
            return rate_error

        # Validate command exists
        if command_class is None:
            unknown = _unknown_command_error(
                f"Command '{display_name}' not found", display_name
            )
            return self._build_error_response(
                code=-32601,  # Method not found
                message=str(unknown),
                request_id=request_id,
                status_code=404,
                data=unknown.data,
            )

        # A protected server takes changes only from an explicit selection
        # (ADR 042, rule D).
        if refusal := self._check_protection(
            command_class, display_name, params, request_id
        ):
            return refusal

        # Prepare arguments and execute
        prepared_args, prepared_extra_args = self._prepare_command_args(
            request, identity, command_class, args, extra_args
        )
        # Off the event loop. `_execute_command` is fully synchronous and runs
        # the command to completion — `subprocess.run`, tar, database work —
        # and the server runs a single worker (server/cli/serve.py), so calling
        # it inline froze auth, the dashboard and every SSE deploy stream for
        # the command's whole duration.
        #
        # Serialized through a one-slot limiter, which keeps today's concurrency
        # exactly: commands already ran one at a time (the loop ran them), and
        # `hop3.lib.console._verbosity` is process-global, so letting two
        # commands run at once would have them overwrite each other's verbosity.
        # Lifting that ceiling means making verbosity a ContextVar first.
        return await self._run_in_slot(
            command_name, prepared_args, prepared_extra_args, request_id
        )

    async def _run_in_slot(
        self,
        command_name: tuple[str, ...],
        args: tuple,
        extra_args: JsonDict,
        request_id: object,
    ) -> Response:
        """Run the command in a worker thread once it holds the command slot."""
        display_name = format_command_name(command_name)
        try:
            async with _COMMAND_SLOT.hold(display_name):
                return await anyio.to_thread.run_sync(
                    self._execute_command, command_name, args, extra_args, request_id
                )
        except ServerBusyError as busy:
            return self._busy_response(busy, display_name, request_id)

    def _busy_response(
        self, busy: ServerBusyError, display_name: str, request_id: object
    ) -> Response:
        """Say which command holds the slot, so a wait never reads as a hang."""
        server_log.warning(
            "RPC call refused: server busy",
            command=display_name,
            running=busy.holder,
            running_for=busy.held_for,
        )
        return self._build_error_response(
            code=RPC_ERROR_SERVER_BUSY,
            message=(
                f"Server busy: {busy.running} and commands run one at a time. "
                f"'hop3 {display_name}' waited {_COMMAND_SLOT.wait_seconds:.0f}s; "
                "retry when it finishes."
            ),
            request_id=request_id,
            status_code=503,
            data={
                "kind": "server_busy",
                "running": busy.holder,
                "running_for": busy.held_for,
            },
        )

    def _validate_envelope(self, data: object, request_id: object) -> Response | None:
        """
        Reject a malformed JSON-RPC envelope with a JSON-RPC error, or None.

        Returns the spec's codes: -32600 for a structurally invalid request,
        -32601 for a method this endpoint does not serve, -32602 for params of
        the wrong shape. Every one of these used to be an unguarded dict access
        that raised and produced an HTML 500 — a response no JSON-RPC client
        can parse — and the method check was an `assert`, which additionally
        vanishes under `python -O`.
        """
        if not isinstance(data, dict):
            return self._build_error_response(
                code=RPC_ERROR_INVALID_REQUEST,
                message="Invalid Request: body must be a JSON object.",
                request_id=request_id,
                status_code=400,
            )

        params = data.get("params")
        params = params if isinstance(params, dict) else {}
        cli_args = params.get("cli_args")
        version = data.get("jsonrpc")
        method = data.get("method")

        # (ok?, code, http status, message) — one row per envelope rule.
        checks: list[tuple[bool, int, int, str]] = [
            (
                version is None or version == "2.0",
                RPC_ERROR_INVALID_REQUEST,
                400,
                f"Invalid Request: unsupported jsonrpc version {version!r}.",
            ),
            (
                method == "cli",
                RPC_ERROR_METHOD_NOT_FOUND,
                404,
                f"Method not found: {method!r}. This endpoint serves 'cli' only.",
            ),
            (
                isinstance(data.get("params"), dict),
                RPC_ERROR_INVALID_PARAMS,
                400,
                "Invalid params: 'params' must be an object.",
            ),
            (
                isinstance(cli_args, list)
                and bool(cli_args)
                and all(isinstance(a, str) for a in cli_args),
                RPC_ERROR_INVALID_PARAMS,
                400,
                "Invalid params: 'cli_args' must be a non-empty list of strings.",
            ),
            (
                params.get("extra_args") is None
                or isinstance(params.get("extra_args"), dict),
                RPC_ERROR_INVALID_PARAMS,
                400,
                "Invalid params: 'extra_args' must be an object.",
            ),
        ]

        for ok, code, status, message in checks:
            if not ok:
                return self._build_error_response(
                    code=code,
                    message=message,
                    request_id=request_id,
                    status_code=status,
                )

        # Optional: clients that predate it send none, and are served as before.
        protocol = params.get("protocol")
        # Exact int: `true == 1` and an unhashable value must not slip past or
        # crash this check into an HTML 500.
        if protocol is not None and not (
            type(protocol) is int and protocol == RPC_PROTOCOL_VERSION
        ):
            return self._build_error_response(
                code=RPC_ERROR_INVALID_REQUEST,
                message=(
                    f"Protocol mismatch: the client speaks /rpc protocol "
                    f"{protocol!r}, this server speaks {RPC_PROTOCOL_VERSION}. "
                    "Upgrade whichever side is older."
                ),
                request_id=request_id,
                status_code=400,
                data={
                    "kind": "protocol_mismatch",
                    "client_protocol": protocol,
                    "server_protocol": RPC_PROTOCOL_VERSION,
                },
            )
        return None

    def _build_error_response(
        self,
        code: int,
        message: str,
        request_id: object,
        status_code: int = 200,
        data: dict | None = None,
    ) -> Response:
        """
        Build a JSON-RPC error response.

        Args:
            code: JSON-RPC error code
            message: Error message
            request_id: Request ID from the original request
            status_code: HTTP status code (default 200 per JSON-RPC spec)
            data: Structured payload for the client (ADR 036 D10 suggestions)

        Returns:
            JSON-RPC error response
        """
        error: dict = {"code": code, "message": message}
        if data:
            error["data"] = data
        error_rpc = {
            "jsonrpc": "2.0",
            "error": error,
            "id": request_id,
        }
        return Response(
            content=json.dumps(error_rpc),
            media_type="application/json",
            status_code=status_code,
            headers=_PROTOCOL_HEADERS,
        )

    def _build_success_response(
        self, result: Json | list[dict], request_id: object
    ) -> Response:
        """
        Build a JSON-RPC success response.

        Args:
            result: Command execution result (can be dict, list, or primitive)
            request_id: Request ID from the original request

        Returns:
            JSON-RPC success response
        """
        result_rpc: dict = {"jsonrpc": "2.0", "result": result, "id": request_id}
        return Response(
            content=json.dumps(result_rpc),
            media_type="application/json",
            headers=_PROTOCOL_HEADERS,
        )

    def _authenticate_and_authorize(
        self,
        request: Request,
        command_class: type[Command] | None,
        display_name: str,
        request_id: object,
    ) -> tuple[Response | None, dict | None]:
        """
        Resolve the caller once; refuse an unauthenticated or unauthorized call.

        Runs in a worker thread: the token check reads the revocation list and
        the role check reads the account. Returns ``(refusal, identity)``, the
        refusal None when the call may proceed. Authentication comes before the
        unknown-command answer, so an anonymous caller learns nothing about
        which commands exist; authorization needs a known command.
        """
        identity = current_identity(request)
        if refusal := self._check_authentication(identity, command_class, request_id):
            return refusal, identity
        if command_class is not None:
            refusal = self._check_authorization(
                identity, command_class, display_name, request_id
            )
        return refusal, identity

    def _check_authentication(
        self,
        identity: dict | None,
        command_class: type[Command] | None,
        request_id: object = None,
    ) -> Response | None:
        """
        Check that the request is authenticated when required.

        The credential is the stateless signed JWT (``current_identity``),
        accepted from the ``Authorization: Bearer`` header (CLI / API) or the
        ``hop3_auth`` cookie (dashboard) — no server-side session.

        Args:
            identity: The validated token payload, or None
            command_class: The command class (may be None if not found)
            request_id: The caller's JSON-RPC id, echoed in the error

        Returns:
            Error response if authentication failed, None if OK
        """
        # Skip authentication enforcement in unsafe testing mode
        if config.HOP3_UNSAFE:
            return None

        # Check if authentication is required
        if command_class is not None and not requires_authentication(command_class):
            return None

        if identity is not None:
            return None

        # Authentication failed
        # -32001, not 401: JSON-RPC error codes are not HTTP status codes, and
        # -32000..-32099 is the range the spec reserves for application errors.
        # The HTTP status stays 401. request_id echoes the caller's id — it was
        # hardcoded to 1, so a client correlating responses saw the wrong one.
        return self._build_error_response(
            code=RPC_ERROR_UNAUTHENTICATED,
            message="Authentication required. Use 'hop3 auth login' to authenticate.",
            request_id=request_id,
            status_code=401,
            # Clients branch on this, never on the prose (hop3_cli.rpc.errors).
            data={"kind": "unauthenticated"},
        )

    def _check_authorization(
        self,
        identity: dict | None,
        command_class: type[Command],
        display_name: str,
        request_id: object,
    ) -> Response | None:
        """
        Refuse a call the caller's account may not make (ADR 061 §3).

        The role comes from the database on every call, never from the token, so
        a demotion or a disabled account takes effect on the next call. A token
        whose subject names no account is refused however it was signed.
        """
        if config.HOP3_UNSAFE or not requires_authentication(command_class):
            return None

        username = str((identity or {}).get("username", ""))
        account = lookup_account(username)

        if account is None or not account.active:
            reason = "does not exist" if account is None else "is disabled"
            server_log.warning(
                "RPC call refused: account", command=display_name, username=username
            )
            return self._build_error_response(
                code=RPC_ERROR_UNAUTHENTICATED,
                message=(
                    f"Your token names account '{username}', which {reason} on "
                    "this server. Sign in again with 'hop3 login'."
                ),
                request_id=request_id,
                status_code=401,
                data={"kind": "account_unusable"},
            )

        role = account.role
        required = command_class.min_role  # ADR 061 §3
        if role.includes(required):
            return None

        server_log.warning(
            "RPC call refused: role",
            command=display_name,
            username=username,
            role=role.value,
            required=required.value,
        )
        hint = f"An admin can grant it: hop3 user set-role {username} {required}"
        return self._build_error_response(
            code=RPC_ERROR_FORBIDDEN,
            message=(
                f"'hop3 {display_name}' needs the {required} role; account "
                f"'{username}' is {role}. {hint}"
            ),
            request_id=request_id,
            status_code=403,
            data={
                "kind": "forbidden",
                "command": display_name,
                "required_role": required.value,
                "role": role.value,
                "hint": hint,
            },
        )

    def _check_protection(
        self,
        command_class: type[Command],
        display_name: str,
        params: JsonDict,
        request_id: object,
    ) -> Response | None:
        """
        Refuse a change to a protected server reached by accident (ADR 042, D).

        The CLI sends ``context_source``, the step of its resolution that chose
        this server, and ``protected_confirmed`` once the operator typed the
        app's name. Checked here rather than in the client, so a stale or
        edited client configuration cannot get around it. Read-only commands,
        and the unauthenticated ones a sign-in needs, are never refused.
        """
        if not config.PROTECTED or not requires_authentication(command_class):
            return None
        if not command_class.min_role.includes(Role.DEPLOYER):
            return None

        source = params.get("context_source")
        if source not in EXPLICIT_CONTEXT_SOURCES:
            server_log.warning(
                "RPC call refused: protected server",
                command=display_name,
                context_source=source,
            )
            hint = "hop3 -c <context> … or export HOP3_CONTEXT=<context>"
            return self._build_error_response(
                code=RPC_ERROR_FORBIDDEN,
                message=(
                    f"This server is protected: 'hop3 {display_name}' changes it, "
                    "so name the server for this command ("
                    f"{hint}). A checkout's binding or the global context never "
                    "selects it for a change. A CLI older than 0.8 does not say "
                    "how it chose the server: upgrade it."
                ),
                request_id=request_id,
                status_code=403,
                data={"kind": PROTECTED_NEEDS_EXPLICIT, "hint": hint},
            )
        if params.get("protected_confirmed") is not True:
            return self._build_error_response(
                code=RPC_ERROR_FORBIDDEN,
                message=(
                    f"This server is protected: 'hop3 {display_name}' needs the "
                    "app's name typed to confirm (or --yes)."
                ),
                request_id=request_id,
                status_code=403,
                data={"kind": PROTECTED_NEEDS_CONFIRMATION},
            )
        return None

    def _check_rate_limit(
        self,
        request: Request,
        command_class: type[Command] | None,
        request_id: object,
    ) -> Response | None:
        """
        Throttle commands that verify a credential without authentication.

        `POST /auth/login` has been rate limited since May 2026, but the same
        password check is reachable over JSON-RPC as `auth get-token`, which
        was not — so the limit could be sidestepped by choosing the other
        transport (audit 2026-07-29 F1/F4). Both paths now draw down the one
        `AUTH_RATE_LIMITER` budget; two limiter instances would have been two
        budgets and no fix at all.

        Args:
            request: HTTP request
            command_class: The command class (may be None if not found)
            request_id: Request ID for the response

        Returns:
            Error response if the caller is over the limit, None if OK
        """
        if command_class is None or not is_rate_limited(command_class):
            return None

        # Mirrors the HOP3_UNSAFE skip in _check_authentication: the flag
        # cannot be set in production (core/unsafe_gate.py forces it off), and
        # test suites log in far faster than 5/min.
        if config.HOP3_UNSAFE:
            return None

        try:
            AUTH_RATE_LIMITER.check(client_ip(request))
        except RateLimitError as e:
            retry_after = int(e.retry_after) + 1
            server_log.warning(
                "Rate limit exceeded on credential-verifying command",
                command=format_command_name(command_class.name),
                retry_after=retry_after,
            )
            return self._build_error_response(
                code=RPC_ERROR_RATE_LIMITED,
                message=f"Too many authentication attempts. Try again in {retry_after}s.",
                request_id=request_id,
                status_code=429,
            )
        return None

    def _prepare_command_args(
        self,
        request: Request,
        identity: dict | None,
        command_class: type[Command],
        args: list[str],
        extra_args: JsonDict,
    ) -> tuple[tuple, JsonDict]:
        """
        Prepare command arguments by injecting username and token info.

        Args:
            request: HTTP request
            identity: The validated token payload, or None
            command_class: The command class
            args: Positional arguments
            extra_args: Keyword arguments

        Returns:
            Tuple of (prepared_args, prepared_extra_args)
        """
        prepared_args = tuple(args)
        prepared_extra_args = extra_args.copy()

        # Pass authenticated username to commands that need it
        if command_needs_username(command_class):
            if identity and identity.get("username"):
                prepared_args = (identity["username"], *prepared_args)

        # Pass token information to commands that need it (e.g., logout)
        if command_needs_token_info(command_class):
            auth_header = request.headers.get("authorization", "")
            # RFC 7235: auth-scheme is case-insensitive
            if auth_header[:7].lower() == "bearer ":
                token = auth_header[7:].strip()
                prepared_extra_args["_token"] = token

        return prepared_args, prepared_extra_args

    def _execute_command(
        self,
        command_name: tuple[str, ...],
        args: tuple,
        extra_args: JsonDict,
        request_id: object,
    ) -> Response:
        """
        Execute the command and return appropriate response.

        Args:
            command_name: Tuple of tokens naming the command
            args: Positional arguments (after the command-name tokens)
            extra_args: Keyword arguments
            request_id: Request ID for the response

        Returns:
            JSON-RPC response (success or error)
        """
        display_name = format_command_name(command_name)
        server_log.info(
            "Executing command",
            command=display_name,
            args=args,
            extra_args_keys=list(extra_args.keys()),
        )
        try:
            result = call(command_name, list(args), extra_args)
            server_log.info(
                "Command completed successfully",
                command=display_name,
                result_type=type(result).__name__,
                result_length=len(result) if isinstance(result, (list, dict)) else None,
            )
            return self._build_success_response(result, request_id)
        except DidYouMeanError as e:
            server_log.error(
                "Command failed with a suggestion",
                command=display_name,
                error=str(e),
                kind=e.data.get("kind"),
            )
            return self._build_error_response(
                code=RPC_ERROR_INVALID_PARAMS,
                message=str(e),
                request_id=request_id,
                data=e.data,
            )
        except (CommandFailedError, Abort) as e:
            # The command ran and failed (disk, subprocess, database), or gave
            # up with an Abort. That is -32603 Internal error, not -32602: the
            # caller's params were fine. Must precede the ValueError arm —
            # CommandFailedError subclasses it. An Abort carries its message in
            # `msg` (its args may be empty) and the hint or the failing
            # command's output in `explanation`: the client needs both.
            message = _abort_message(e) if isinstance(e, Abort) else str(e)
            server_log.error(
                "Command failed while executing",
                command=display_name,
                error=message,
            )
            traceback.print_exc()
            return self._build_error_response(
                code=RPC_ERROR_INTERNAL,
                message=message,
                request_id=request_id,
            )
        except ValueError as e:
            # A genuine bad-argument error raised by the command's own parsing.
            server_log.error(
                "Command rejected its arguments",
                command=display_name,
                error=str(e),
            )
            traceback.print_exc()
            return self._build_error_response(
                code=RPC_ERROR_INVALID_PARAMS,
                message=str(e),
                request_id=request_id,
            )
        except RepositoryError as e:
            # Unwrap the advanced_alchemy wrapper into a structured Diagnosis
            # so the CLI can render component/reason/hint instead of a generic
            # "There was an error during data processing" string.
            diag = _repository_error_diagnosis(e)
            error_msg = format_diagnosis(diag)
            server_log.error(
                "Command failed with RepositoryError",
                command=display_name,
                error_type=type(e).__name__,
                reason=diag.reason,
                original_error=str(e.__cause__) if e.__cause__ else None,
            )
            traceback.print_exc()
            return self._build_error_response(
                code=RPC_ERROR_INTERNAL,
                message=error_msg,
                request_id=request_id,
            )
        except Exception as e:
            server_log.error(
                "Command failed with exception",
                command=display_name,
                error_type=type(e).__name__,
                error=str(e),
            )
            traceback.print_exc()
            return self._build_error_response(
                code=RPC_ERROR_INTERNAL,
                message=f"{type(e).__name__}: {e!s}",
                request_id=request_id,
            )


def _abort_message(abort: Abort) -> str:
    """An Abort's message followed by its explanation, when it has one."""
    if not abort.explanation:
        return abort.msg
    return f"{abort.msg}\n{abort.explanation}"
