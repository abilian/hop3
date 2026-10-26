# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Login command - authenticate to a Hop3 server."""

from __future__ import annotations

import dataclasses
import getpass
import os
import sys
from typing import TYPE_CHECKING, assert_never
from urllib.parse import parse_qs, urlparse

from jsonrpcclient import Error, Ok

from hop3_cli.config import DEFAULT_CONTEXT_NAME, ENV_CONTEXT_NAME, Config
from hop3_cli.core.ssh_target import is_safe_ssh_target, ssh_target_from_address
from hop3_cli.exit_codes import ExitCode
from hop3_cli.tokens import bearer_header, extract_jwt

from .help_text import print_login_help
from .ssh_ops import (
    BootstrapError,
    FallbackReason,
    get_magic_link_via_ssh,
    get_ssh_token,
    get_token_via_ssh,
    host_from_ssh_target,
    server_url_and_reason,
    ssh_user,
    web_base_url,
)

if TYPE_CHECKING:
    from jsonrpcclient.responses import Response

    from hop3_cli.ui.rich_printer import RichPrinter

#: Seconds to wait when probing a server's HTTPS endpoint, before a login
#: decides whether to record it as the everyday address.
HTTPS_PROBE_TIMEOUT = 10


def handle_login(args: list[str], config: Config, printer: RichPrinter) -> None:
    """
    Handle the login command.

    The axis is which client receives a credential: this CLI by default, the
    browser with ``--browser``. Both bootstrap over SSH, which is why naming
    the transport in a flag said nothing.

    Usage:
        hop3 login user@server                           # this CLI, over SSH
        hop3 login --context <name>                      # its recorded SSH route
        hop3 login --browser [user@server]               # a link for the browser
        hop3 login "http://localhost:8000?token=eyJ..."  # URL with embedded token
        hop3 login --token <token> --url <url>           # Separate token and server
        hop3 login                                       # Username/password auth
    """
    # Check for help first
    if "--help" in args or "-h" in args:
        print_login_help()
        return

    # Check for URL with embedded token (e.g., http://localhost:8000?token=eyJ...)
    if args and not args[0].startswith("-"):
        potential_url = args[0]
        if "?" in potential_url and "token=" in potential_url:
            parsed = urlparse(potential_url)
            query_params = parse_qs(parsed.query)
            if "token" in query_params:
                token = query_params["token"][0]
                # Reconstruct server URL without the token parameter
                server_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                handle_login_token(
                    ["--token", token, "--url", server_url], config, printer
                )
                return

    # Dispatch based on which client gets a credential.
    if is_browser_form(args):
        handle_login_web(args, config, printer)
    elif "--token" in args:
        handle_login_token(args, config, printer)
    elif ssh_target_argument(args) or "--ssh" in args:
        handle_login_ssh(args, config, printer)
    elif "--username" not in args and (target := _recorded_ssh_target(config)):
        handle_login_ssh([target, *args], config, printer)
    else:
        # Default: password-based authentication
        handle_login_password(args, config, printer)


def _recorded_ssh_target(config: Config) -> str | None:
    """
    The SSH route the context named by ``--context`` already records, if any.

    `hop3 login --context dev`, for a context whose server is ``ssh://``, asked
    for a username and password: without a target on the line, the login fell
    through to the password form, though the context said where to go.
    """
    name = config.get_context_override()
    bootstrap = config.get_context_bootstrap(name) if name else None
    if not bootstrap:
        return None
    return ssh_target_from_address(bootstrap, config.get("ssh_user", "root"))


#: The old spellings. `--ssh` named a transport and `--browser`'s predecessor
#: `--web` named a destination, so they read as alternatives on one axis when
#: they were on two — and both travel over SSH regardless. The surviving axis
#: is *which client receives a credential*: this CLI by default, the browser
#: with `--browser`. Both old flags still dispatch, hidden.
BROWSER_FLAGS = ("--browser", "--web")


def is_browser_form(args: list[str]) -> bool:
    """Whether this login is for the browser rather than for this CLI."""
    return any(flag in args for flag in BROWSER_FLAGS)


def ssh_target_argument(args: list[str]) -> str | None:
    """
    The positional ``[user@]host[:port]`` of a bootstrap login, if there is one.

    SSH is the only transport either login form has, so naming it in a flag said
    nothing. A bare target is the form now: ``hop3 login root@prod.example.com``.
    A URL is not one — ``hop3 login https://…`` and the ``?token=`` spelling are
    handled above — and neither is a flag or its value.
    """
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg.startswith("-"):
            skip_next = arg in _LOGIN_VALUE_FLAGS
            continue
        if index and args[index - 1] in _LOGIN_VALUE_FLAGS:
            continue
        if "://" in arg or "?" in arg:
            return None
        if is_safe_ssh_target(arg):
            return arg
        return None
    return None


#: Login flags that take a value, so the value is never read as the target.
#: `--context` is absent on purpose: `parse_flags` consumes it as a global flag
#: before `handle_login` ever sees argv.
_LOGIN_VALUE_FLAGS = ("--username", "--url", "--token")


def handle_logout(args: list[str], config: Config, printer: RichPrinter) -> None:
    """
    Log out: revoke the token on the server and clear it locally.

    Usage:
        hop3 logout        # or: hop3 auth logout
    """
    if "--help" in args or "-h" in args:
        print(
            "hop3 logout — Log out and clear the local token.\n\n"
            "Revokes the current token on the server (so it can't be reused) and\n"
            "removes it from this machine's config. Alias of `hop3 auth logout`."
        )
        return

    if not config.get_api_token():
        print("Not logged in (no local token to clear).")
        return

    # Revoke server-side first, while the token is still in the store so the
    # request can authenticate. We surface a revoke failure loudly but still
    # clear the local token — logging out of THIS machine must always succeed.
    from hop3_cli.rpc import Client  # ruff:ignore[import-outside-top-level]

    revoke_failed: str | None = None
    try:
        with Client(config=config) as client:
            client.rpc("cli", ["auth", "logout"])
    except Exception as e:
        # Network/server errors here are non-fatal: we still clear the local
        # token so logging out of THIS machine always succeeds.
        revoke_failed = str(e)

    # Clear the token from the per-server credential store (no-op if absent).
    config.update_context_token("")

    if revoke_failed:
        print(
            "Local token cleared, but the server could not revoke it: "
            f"{revoke_failed}\n"
            "The token stays valid on the server until it expires.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Logged out. Token revoked on the server and cleared locally.")


def handle_login_password(
    args: list[str], config: Config, printer: RichPrinter
) -> None:
    """
    Handle password-based login via the server API.

    Usage:
        hop3 login
        hop3 login --username admin
    """
    _ensure_server_configured(config)
    username = _parse_username_arg(args)
    username, password = _prompt_credentials(username)

    # Verify the password and mint a token via the server's get-token primitive.
    print(f"\nAuthenticating as {username}...")

    # Import here to avoid circular import
    from hop3_cli.rpc import Client  # ruff:ignore[import-outside-top-level]

    with Client(config=config) as client:
        try:
            response = client.rpc("cli", ["auth", "get-token", username, password])
            _handle_login_response(response, username, config, printer)

        except Exception as e:
            print(f"Error during login: {e}", file=sys.stderr)
            sys.exit(1)


def _ensure_server_configured(config: Config) -> None:
    """Check if server is configured, exit with help if not."""
    if config.is_configured():
        return

    config.require_target()  # raises the refusal that says why there is none


def _parse_username_arg(args: list[str]) -> str | None:
    """Parse --username argument from args."""
    i = 0
    while i < len(args):
        if args[i] == "--username" and i + 1 < len(args):
            return args[i + 1]
        i += 1
    return None


def _prompt_credentials(username: str | None) -> tuple[str, str]:
    """Prompt for username and password, return both."""
    from hop3_cli.exit_codes import ExitCode  # ruff:ignore[import-outside-top-level]
    from hop3_cli.ui.prompts import (  # ruff:ignore[import-outside-top-level]
        NoInputError,
        require_input_allowed,
    )

    if not username:
        try:
            require_input_allowed("login")
        except NoInputError as e:
            print(
                f"Error: {e}\n  Use --username <name> with credentials piped or set in env.",
                file=sys.stderr,
            )
            sys.exit(ExitCode.USAGE_ERROR)
        username = input("Username: ").strip()
        if not username:
            print("Error: Username cannot be empty", file=sys.stderr)
            sys.exit(ExitCode.USAGE_ERROR)

    try:
        require_input_allowed("password entry")
    except NoInputError as e:
        print(
            f"Error: {e}\n  Use HOP3_PASSWORD env var or pipe via --password-file -.",
            file=sys.stderr,
        )
        sys.exit(ExitCode.USAGE_ERROR)
    password = getpass.getpass("Password: ")
    if not password:
        print("Error: Password cannot be empty", file=sys.stderr)
        sys.exit(ExitCode.USAGE_ERROR)

    return username, password


def _handle_login_response(
    response: Response, username: str, config: Config, printer: RichPrinter
) -> None:
    """Handle the RPC response from the password path's `auth get-token` call."""
    match response:
        case Ok(result=result):
            token = _extract_token_from_login_response(result)
            if token:
                # Password login runs against an already-configured server
                # (_ensure_server_configured ran first), so the connection
                # address is known; stash the token in its per-server store.
                server_url = config.get_api_url()
                if not server_url:
                    print(
                        "Error: no server configured. Run `hop3 login <user>@<host>` first.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                record_server_login(config, server_url, token)
                print(f"Logged in as {username}")
            else:
                printer.print(result)
        case Error(message=message):
            print(f"Login failed: {message}", file=sys.stderr)
            sys.exit(1)
        case _ as unreachable:
            assert_never(unreachable)


def _extract_token_from_login_response(result: list[dict]) -> str | None:
    """
    Extract the JWT token from the `auth get-token` response.

    Args:
        result: The RPC response from `auth get-token`

    Returns:
        The JWT token or None if not found
    """
    for item in result:
        if item.get("t") == "text":
            text = item.get("text", "")
            token = extract_jwt(text)
            if token:
                return token
    return None


def handle_login_web(args: list[str], config: Config, printer: RichPrinter) -> None:
    """
    Handle --web flag to generate a magic link for browser login.

    This generates a short-lived, single-use URL that can be used to log into
    the web dashboard without entering a password. Requires SSH access.

    Usage:
        hop3 login --browser                    # Uses current context
        hop3 login --browser server.com         # SSH as root@server.com
        hop3 login --browser user@server.com    # SSH as user@server.com
    """
    ssh_target, username = _parse_login_web_args(args, config)

    print(f"\nConnecting to {ssh_target}...")

    try:
        result = get_magic_link_via_ssh(ssh_target, username)
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # The server returns a full URL when it has a public admin domain (it knows
    # its own scheme/host then). Otherwise it returns a bare token and we build
    # the URL from the server we actually reach — preserving https for a
    # TLS-fronted host instead of guessing http://host:8000.
    if result.startswith(("http://", "https://")):
        magic_link = result
    else:
        # A bare token means the server has no ADMIN_DOMAIN: `auth:magic-link`
        # emits a full URL only when it has one. There is then no TLS vhost for
        # the dashboard, and its session cookie is `Secure` — so the link we are
        # about to build cannot work. Say so before handing it over, rather than
        # letting the browser fail with nothing to explain it.
        base = web_base_url(_resolved_server_url(config), ssh_target)
        magic_link = f"{base}/auth/magic/{result}"
        _warn_dashboard_unreachable(ssh_target, base)

    print()
    print("Magic link generated!")
    print()
    print("Open this URL in your browser to log in:")
    print()
    print(f"  {magic_link}")
    print()
    print("Note: This link expires in 5 minutes and can only be used once.")


def _warn_dashboard_unreachable(ssh_target: str, base: str) -> None:
    """The dashboard has no HTTPS endpoint; the link below will not open."""
    host = host_from_ssh_target(ssh_target)
    print(
        f"\n  warning: {host} has no admin domain, so the dashboard is not served "
        f"over HTTPS.\n"
        f"           Its session cookie is Secure, so signing in at {base} cannot "
        f"hold a session\n"
        f"           and the link below will not work.\n"
        f"           {admin_domain_advice(host)}",
        file=sys.stderr,
    )


def _parse_login_web_args(args: list[str], config: Config) -> tuple[str, str]:
    """
    Parse arguments for the browser form.

    Returns:
        Tuple of (ssh_target, username)
    """
    username = "admin"  # Default to admin user
    for index, arg in enumerate(args):
        if arg == "--username" and index + 1 < len(args):
            username = args[index + 1]
            break

    # The target is optional: bare `--browser` uses the current context, which
    # is the everyday case once you have logged in. An explicit one is what
    # makes the form work on a machine that has no context yet.
    ssh_target = ssh_target_argument(args) or _get_ssh_target_from_config(config)

    if not ssh_target:
        print(
            "Error: no server to ask for a dashboard link, and none configured.\n"
            "\n"
            "  hop3 login --browser root@server.com   # name one\n"
            "  hop3 login root@server.com             # or sign this CLI in first",
            file=sys.stderr,
        )
        sys.exit(ExitCode.USAGE_ERROR)

    # Ensure SSH target has user@ prefix (default to root)
    if "@" not in ssh_target:
        ssh_target = f"root@{ssh_target}"

    return ssh_target, username


def _resolved_server_url(config: Config) -> str | None:
    """
    The server URL the login should target — without aborting.

    An explicit ``--context <name>`` selects that context's server (project-less,
    global): it is the single selector every command honours (ADR 042), and a
    *local* command like ``login`` must honour it too. Local commands dispatch
    before ``main`` wires the active server, so ``get_api_url()`` alone ignores
    ``--context`` — which is why ``--context prod login --browser`` used to hit the
    default server. Falls back to the configured/default server. Returns None if
    the named context isn't defined (the caller decides whether that is fatal).
    """
    override = config.get_context_override()
    if override:
        return config.get_context_server(override)
    return config.get_api_url()


def _get_ssh_target_from_config(config: Config) -> str | None:
    """
    Extract SSH target from the current context's API URL.

    Handles both SSH URLs (ssh://root@host) and HTTP URLs (https://host). An
    explicit ``--context`` that names no known context is a hard error here
    rather than a silent fall-through to the default server.
    """
    override = config.get_context_override()
    api_url = _resolved_server_url(config)
    if override and not api_url:
        known = ", ".join(sorted(config.list_global_contexts())) or "(none)"
        print(
            f"Error: context {override!r} is not defined.\n"
            f"  Known contexts: {known}\n"
            f"  Define it with:  hop3 login --context {override} --ssh root@<server>",
            file=sys.stderr,
        )
        sys.exit(1)
    if not api_url:
        return None

    parsed = urlparse(api_url)

    if parsed.scheme == "ssh":
        # ssh://root@host -> root@host
        if parsed.username:
            return f"{parsed.username}@{parsed.hostname}"
        return f"root@{parsed.hostname}"

    if parsed.scheme in {"http", "https"}:
        # https://host -> root@host
        return f"root@{parsed.hostname}"

    return None


def refuse_unnamed_retarget(
    config: Config, server_url: str, name: str = DEFAULT_CONTEXT_NAME
) -> None:
    """
    Refuse to repoint the `default` context at a different server, unasked.

    Only when the operator named nothing. `--context prod` is a deliberate
    choice and repoints with an announcement; an unnamed login cannot tell
    "I replaced my server" from "I have two now", and quietly answering with
    the first is how `hop3 apps` starts reporting on the wrong machine.

    Re-logging the same address is a token refresh and passes through.
    """
    if name != DEFAULT_CONTEXT_NAME or config.get_context_override():
        return
    current = config.get_context_server(DEFAULT_CONTEXT_NAME)
    if not current or current == server_url:
        return
    # Two routes to one machine is the common case, not the exception: the
    # deployer writes `default` -> http://<host>:8000 at the end of every
    # deploy, and the login it then suggests is ssh://root@<host>. Reading
    # those as two servers is the reader's obvious first guess, and it is
    # wrong — so say whose they are before offering the remedies.
    same_host = _hostname(current) == _hostname(server_url) != ""
    whose = (
        f"\nBoth reach {_hostname(server_url)}, by different routes — the first"
        f"\nwas written when the server was deployed.\n"
        if same_host
        else ""
    )
    print(
        f"Hop3 won't repoint the {DEFAULT_CONTEXT_NAME!r} context.\n"
        f"\n"
        f"  it names   {current}\n"
        f"  this login is for {server_url}\n"
        f"{whose}"
        f"\nKeep both, or replace the old one:\n"
        f"\n"
        f"  hop3 login … --context <name>\n"
        f"  hop3 context remove {DEFAULT_CONTEXT_NAME}",
        file=sys.stderr,
    )
    sys.exit(ExitCode.GENERAL_ERROR)


def _hostname(url: str) -> str:
    """The host an address points at, for telling one server from two."""
    parsed = urlparse(url if "://" in url else f"//{url}")
    return parsed.hostname or ""


def record_server_login(
    config: Config, server_url: str, token: str, *, bootstrap: str | None = None
) -> None:
    """
    ADR 042: store the token, and create or update the context it belongs to.

    This is the *only* place a login persists credentials: the token goes to the
    per-server credential store (keyed by canonical address); config.toml stays
    secret-free. The context is the one ``--context`` names, else the one this
    invocation targets when the login is for its server, else ``default``.

    Authenticating never changes where commands go: the login makes its
    context the global current context only when there is none, and otherwise
    prints the command that would.
    """
    if not server_url:
        return

    context_name = _login_context_name(config, server_url)
    refuse_unnamed_retarget(config, server_url, context_name)

    from hop3_cli.core import credential_store  # ruff:ignore[import-outside-top-level]

    from .completion_cmd import (  # ruff:ignore[import-outside-top-level]
        refresh_caches_after_login,
    )

    credential_store.set_token(server_url, token)

    # A successful login is a lie if an exported HOP3_API_TOKEN keeps shadowing
    # it (get_api_token returns the env var first). Surface it so the user isn't
    # left acting as the wrong identity (audit 2026-06 C4).
    if os.environ.get("HOP3_API_TOKEN"):
        print(
            "  warning: HOP3_API_TOKEN is set in your environment and overrides "
            "this stored token for every command until you `unset HOP3_API_TOKEN`.",
            file=sys.stderr,
        )

    # The same lie, one rank higher: `Config.get_api_url` checks HOP3_API_URL
    # before any context, so a stale export sends every later command somewhere
    # else entirely and this login applies to nothing. Only worth saying when
    # the two disagree — CI that exports the server it just logged into is fine.
    env_url = config.env_context_server()
    if env_url and env_url != server_url:
        print(
            f"  warning: the {ENV_CONTEXT_NAME!r} context ({env_url}) comes from "
            f"your environment and overrides this login's target ({server_url}) "
            f"for every command until you unset HOP3_API_URL.",
            file=sys.stderr,
        )

    # Read what it was BEFORE writing, or the comparison below always matches.
    previous_context = config.get_default_context()
    previous_server = config.get_context_server(context_name)
    config.set_context_server(context_name, server_url, bootstrap=bootstrap)
    if not previous_context:
        config.set_default_context(context_name)
    # The context is on disk now, but this process resolved its connection
    # before the login wrote it, so everything after this point in the same
    # invocation still sees the pre-login answer. `refresh_caches_after_login`
    # below asked `get_api_url()` and was told "API URL not configured" — one
    # line under "Signed in to …", about the server it had just signed in to.
    config.set_active_server(server_url)
    config.set_active_bootstrap(bootstrap)
    # Only what changed. A repeat login of the same target says nothing extra;
    # a switch of the current context, or a context that now points somewhere
    # else, is exactly what an operator must not discover by surprise later.
    if not previous_context:
        print(f"  context {context_name!r} is now the global current context")
    elif previous_context != context_name:
        print(
            f"  context {context_name!r} recorded; the global current context "
            f"stays {previous_context!r}. Use it: hop3 context use {context_name}"
        )
    if previous_server and previous_server != server_url:
        print(f"  context {context_name!r}: {previous_server} -> {server_url}")

    # Now that there is a server to ask, fill the caches shell completion and
    # the offline command list read from (ADR 036 M9.3).
    refresh_caches_after_login(config)


def _login_context_name(config: Config, server_url: str) -> str:
    """The context a login for ``server_url`` records its server under."""
    if override := config.get_context_override():
        return override
    target = config.get_target()
    # `env` is the environment's own target, never a stored context.
    if (
        target is not None
        and target.context != ENV_CONTEXT_NAME
        and target.server == server_url
    ):
        return target.context
    return DEFAULT_CONTEXT_NAME


def handle_login_token(args: list[str], config: Config, printer: RichPrinter) -> None:
    """
    Handle token-based login for local development or automation.

    Usage:
        hop3 login --token <token> --url http://localhost:8000
        hop3 login --token <token>  # Uses existing server config
    """
    token, server_url = _parse_token_args(args)
    server_url = _resolve_server_url(server_url, config)

    # Verify connection before saving
    username = _verify_token(server_url, token)
    if not username:
        sys.exit(1)

    # Save credentials only after successful verification: token to the
    # per-server store, server as the default target. config.toml stays
    # secret-free (ADR 042 r2).
    record_server_login(config, server_url, token)
    print(f"\nLogged in as {username}")
    print(f"Token stored for {server_url}")


def _parse_token_args(args: list[str]) -> tuple[str, str | None]:
    """Parse --token and --url arguments."""
    token = None
    server_url = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--token" and i + 1 < len(args):
            token = args[i + 1]
            i += 2
        elif arg == "--url" and i + 1 < len(args):
            server_url = args[i + 1]
            i += 2
        else:
            i += 1

    if not token:
        print_login_help()
        print("\nError: --token requires a token value", file=sys.stderr)
        sys.exit(1)

    # Type narrowing: token is str after the check above
    assert token is not None

    if not token.startswith("eyJ"):
        print("Warning: Token doesn't look like a JWT token", file=sys.stderr)

    return token, server_url


def _resolve_server_url(server_url: str | None, config: Config) -> str:
    """Resolve server URL from argument, config, or prompt."""
    if server_url:
        return server_url

    # Try to get URL from current context
    existing_url = config.get_api_url()
    if existing_url:
        print(f"Using existing server: {existing_url}")
        return existing_url

    # Prompt for URL
    if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
        default_url = "http://localhost:8000"
    else:
        default_url = "https://your-server.com"

    return input(f"Server URL [{default_url}]: ").strip() or default_url


def _verify_token(server_url: str, token: str) -> str | None:
    """
    Verify token by calling auth whoami on the server.

    Returns:
        Username if successful, None if verification failed
    """
    # Import here to avoid circular import
    from hop3_cli.rpc import Client  # ruff:ignore[import-outside-top-level]

    temp_config = _ProbeConfig(probe_url=server_url, probe_token=token)

    print(f"Verifying connection to {server_url}...")

    try:
        with Client(config=temp_config) as client:
            response = client.rpc("cli", ["auth", "whoami"])

            match response:
                case Ok(result=result):
                    # Extract username from response
                    return _extract_username_from_whoami(result)
                case Error(message=message):
                    print(f"Authentication failed: {message}", file=sys.stderr)
                    return None
                case _ as unreachable:
                    assert_never(unreachable)

    except Exception as e:
        error_str = str(e).lower()
        # Check for connection-related errors
        if "connection refused" in error_str or "failed to establish" in error_str:
            print(f"Could not connect to {server_url}", file=sys.stderr)
            print("Is the server running?", file=sys.stderr)
        elif "timeout" in error_str:
            print(f"Connection to {server_url} timed out.", file=sys.stderr)
            print("The server may be slow or unreachable.", file=sys.stderr)
        elif "ssl" in error_str or "certificate" in error_str:
            print(f"SSL/TLS error connecting to {server_url}", file=sys.stderr)
            print(
                "Check that the server URL is correct (http vs https).", file=sys.stderr
            )
        else:
            print(f"Could not connect to {server_url}", file=sys.stderr)
        return None


@dataclasses.dataclass
class _ProbeConfig(Config):
    """
    A config that connects to exactly the server and token under verification.

    A config's own token ranks below the per-server credential store and
    ``HOP3_API_TOKEN``, and its URL below ``HOP3_API_URL``. So a login check
    built from an ordinary config sent whatever was already stored for that
    server: after a `hop3-deploy-server --docker --clean`, the token from the
    previous container, signed with a key that no longer exists. The new token
    was refused with "Authentication required" without ever being sent.
    """

    probe_url: str = ""
    probe_token: str = ""

    def get_api_url(self) -> str | None:
        return self.probe_url

    def get_api_token(self) -> str | None:
        return self.probe_token


def _extract_username_from_whoami(result: list[dict]) -> str | None:
    """Extract username from auth whoami response."""
    for item in result:
        if item.get("t") == "text":
            text = item.get("text", "")
            # Look for "Logged in as: username" or similar patterns
            if "Logged in as:" in text:
                parts = text.split("Logged in as:")
                if len(parts) > 1:
                    return parts[1].strip().split()[0]
            # Fallback: return first non-empty word
            words = text.strip().split()
            if words:
                return words[0]
    return "user"  # Default if we can't extract


def _determine_save_url(
    api_url: str | None,
    ssh_target: str,
    token: str,
    config: Config,
    debug_level: int,
) -> tuple[str, str | None]:
    """
    The ``(everyday address, bootstrap address)`` to record for this login.

    SSH is how a token is minted; it is not how routine work should travel.
    Recording ``ssh://root@host`` as the connection — as every SSH login used
    to — sent `hop3 apps`, `hop3 logs` and every other read through a root
    shell, once per invocation. So the server is asked for its own public
    address and that becomes the everyday one, with the SSH target kept as the
    bootstrap route so an expired token still renews unattended.

    The SSH tunnel remains the answer when the server has no HTTPS endpoint to
    offer, and the operator is told why.
    """
    if api_url:
        # User explicitly provided URL - use HTTP API
        if debug_level >= 1:
            print(f"[debug] Will use HTTP API at: {api_url}")
        # For HTTPS, verify the connection works with system CA bundle
        # (aborts the login on an untrusted certificate). The operator named
        # this URL, so a broken one is a mistake to surface, not to route past.
        if api_url.startswith("https://"):
            config_data = {"api_url": api_url, "api_token": token}
            _verify_https_connection(api_url, token, config, config_data, debug_level)
        return api_url, _build_ssh_url(ssh_target)

    ssh_url = _build_ssh_url(ssh_target)
    public_url, reason = server_url_and_reason(ssh_target)
    if public_url:
        if problem := _https_unusable_because(public_url, token):
            _explain_ssh_fallback(ssh_target, f"{public_url} {problem}")
            return ssh_url, None
        if debug_level >= 1:
            print(f"[debug] Will use the server's public URL: {public_url}")
        return public_url, ssh_url

    assert reason is not None  # no URL means the probe said why
    _explain_ssh_fallback(ssh_target, _FALLBACK_DETAIL[reason], advice=reason)
    return ssh_url, None


#: How each reason reads in the note the operator sees.
_FALLBACK_DETAIL: dict[FallbackReason, str] = {
    FallbackReason.NO_ADMIN_DOMAIN: (
        "it has no admin domain, so there is no HTTPS endpoint"
    ),
    FallbackReason.OUTDATED_SERVER: "it is too old to report its public address",
}


def _https_unusable_because(api_url: str, token: str) -> str:
    """``""`` when the URL answers over TLS this machine trusts, else why not.

    Deliberately not ``_verify_https_connection``, which aborts: there the
    operator named the URL and a broken one is their mistake to see. Here the
    *server* proposed it and a working fallback exists, so this reports and the
    caller decides. Any HTTP answer counts — a 401 still proves TLS and reach.
    """
    import requests  # ruff:ignore[import-outside-top-level]

    try:
        requests.get(
            f"{api_url.rstrip('/')}/health",
            headers={"Authorization": bearer_header(token)},
            timeout=HTTPS_PROBE_TIMEOUT,
            verify=True,
        )
    except requests.exceptions.SSLError:
        return "has a certificate this machine does not trust"
    except requests.exceptions.RequestException:
        return "is not reachable from here"
    return ""


def _explain_ssh_fallback(
    ssh_target: str, detail: str, *, advice: FallbackReason | None = None
) -> None:
    """
    Say that everyday traffic will tunnel over SSH, and why.

    ``detail`` is already worded — the caller knows whether it is describing a
    reason the probe reported or a certificate it could not verify, so this
    does not re-derive it from a string that carried three different shapes.

    A silent fallback here is the worst outcome: the operator keeps a working
    CLI and never learns that every command opens a root shell, nor that the
    dashboard is unreachable for the same reason.
    """
    print(
        f"\n  note: every command will tunnel over SSH as {ssh_user(ssh_target)}, "
        f"because {detail}.",
        file=sys.stderr,
    )
    if advice is FallbackReason.NO_ADMIN_DOMAIN:
        host = host_from_ssh_target(ssh_target)
        print(f"        {admin_domain_advice(host)}", file=sys.stderr)


def admin_domain_advice(host: str) -> str:
    """
    The single fix for both consequences of having no admin domain.

    Without one there is no TLS vhost: the API has no HTTPS endpoint *and* the
    dashboard cannot hold a session, because its cookie is `Secure`. One cause,
    so one sentence, shared by the login and the dashboard-link paths.
    """
    return (
        f"Give it one to serve the API and the dashboard over HTTPS: "
        f"hop3-deploy-server --host {host} --admin-domain <fqdn>"
    )


def handle_login_ssh(args: list[str], config: Config, printer: RichPrinter) -> None:
    """
    Handle the SSH bootstrap: mint a token and record where commands go.

    SSH access is the authentication - no username/password needed by default.
    If --username is provided, uses the legacy flow for that specific user.

    Usage:
        hop3 login user@server                    # Auto-auth (recommended)
        hop3 login user@server --username admin   # Specific user (legacy)
        hop3 login user@server --url https://...  # Name the HTTP API explicitly
        hop3 login user@server -d                 # Show debug info
    """
    ssh_target, username, api_url, debug_level = _parse_login_ssh_args(args)

    if debug_level >= 1:
        print(f"[debug] SSH target: {ssh_target}")
        print(f"[debug] Username: {username or '(auto)'}")
        print(f"[debug] API URL override: {api_url or '(none, will use SSH tunnel)'}")

    print(f"\nConnecting to {ssh_target}...")

    try:
        if username:
            # Legacy flow: get token for specific user
            token = get_token_via_ssh(ssh_target, username)
            display_username = username
        else:
            # New simplified flow: SSH access = admin access
            token = get_ssh_token(ssh_target)
            display_username = "admin"  # Default user created/used by admin:ssh-token
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if debug_level >= 2:
        print(f"[debug] Token received: {token[:20]}...{token[-10:]}")

    # Determine API URL to save
    save_url, bootstrap_url = _determine_save_url(
        api_url, ssh_target, token, config, debug_level
    )

    record_server_login(config, save_url, token, bootstrap=bootstrap_url)
    if debug_level >= 1:
        print(f"[debug] Token stored for: {save_url}")
        print(f"[debug] Bootstrap route: {bootstrap_url or '(none)'}")

    _print_login_success(
        display_username,
        save_url,
        config.get_context_override() or DEFAULT_CONTEXT_NAME,
    )


def _build_ssh_url(ssh_target: str) -> str:
    """
    Build SSH URL from SSH target.

    Args:
        ssh_target: SSH target (user@host or host)

    Returns:
        SSH URL for the API (e.g., ssh://root@hop3.dev)
    """
    if "@" in ssh_target:
        return f"ssh://{ssh_target}"
    return f"ssh://root@{ssh_target}"


def _parse_login_ssh_args(args: list[str]) -> tuple[str, str | None, str | None, int]:
    """
    Parse arguments for the SSH bootstrap form.

    Returns:
        Tuple of (ssh_target, username, api_url, debug_level)
    """
    ssh_target = None
    username = None
    api_url = None
    debug_level = 0

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--ssh" and i + 1 < len(args):
            ssh_target = args[i + 1]
            i += 2
        elif arg == "--username" and i + 1 < len(args):
            username = args[i + 1]
            i += 2
        elif arg == "--url" and i + 1 < len(args):
            api_url = args[i + 1]
            i += 2
        elif arg.startswith("-d"):
            # Count consecutive 'd's: -d = 1, -dd = 2, -ddd = 3
            debug_level += arg.count("d")
            i += 1
        else:
            i += 1

    # The positional form: `hop3 login root@server.com`. `--ssh` is the old
    # spelling of the same thing and still works.
    ssh_target = ssh_target or ssh_target_argument(args)

    if not ssh_target:
        print_login_help()
        print(
            "\nError: this form needs a target, e.g. `hop3 login root@server.com`.",
            file=sys.stderr,
        )
        sys.exit(1)

    return ssh_target, username, api_url, debug_level


def _verify_https_connection(
    api_url: str,
    token: str,
    config: Config,
    config_data: dict,
    debug_level: int = 0,
) -> None:
    """
    Verify HTTPS connection works with the system CA bundle.

    Aborts the login (exit AUTH_ERROR) when the certificate is untrusted, so
    we never persist an https config that would fail on every later call.

    Args:
        api_url: The HTTPS URL to verify
        token: The API token for authentication
        config: Config object for saving settings
        config_data: Config data dict to update
        debug_level: Debug verbosity level
    """
    import requests  # ruff:ignore[import-outside-top-level]

    from hop3_cli.exit_codes import ExitCode  # ruff:ignore[import-outside-top-level]

    if debug_level >= 1:
        print(f"[debug] Verifying HTTPS connection to {api_url}")

    try:
        # Try to connect with system CA bundle
        response = requests.get(
            f"{api_url.rstrip('/')}/health",
            headers={"Authorization": bearer_header(token)},
            timeout=HTTPS_PROBE_TIMEOUT,
            verify=True,  # Use system CA bundle
        )
        if response.ok:
            print("HTTPS connection verified ✓")
        else:
            print(f"HTTPS connection works (status: {response.status_code})")

    except requests.exceptions.SSLError:
        # Self-signed or untrusted certificate. We deliberately do NOT
        # offer an interactive "disable verification?" prompt here:
        # auth tokens flow over this connection and a single typo'd
        # 'y' would silently drop them onto an attacker-in-the-middle.
        # The operator can still opt in via the persistent config knob,
        # which is a deliberate, audit-able decision.
        host = _extract_host(api_url)
        msg = (
            "\nThe server uses a self-signed or untrusted SSL certificate.\n"
            "Refusing to log in: a wrong choice here would leak your auth\n"
            "token on every subsequent CLI call.\n"
            "\nResolve one of these ways:\n"
            "  1. Use an SSH tunnel (recommended — bypasses TLS entirely):\n"
            f"       hop3 login {host}\n"
            "  2. Trust the server certificate explicitly:\n"
            "       hop3 settings set ssl_cert /path/to/server.crt\n"
            "  3. Disable verification for this server (last resort):\n"
            "       hop3 settings set verify_ssl false\n"
            "       hop3 login ...   # retry"
        )
        # Actually abort. Printing "Refusing to log in" and then letting the
        # caller persist the https URL anyway produced a self-contradictory
        # flow ("Refusing..." followed by "Credentials saved") and a config
        # that fails SSL verification on every subsequent call.
        print(msg, file=sys.stderr)
        sys.exit(ExitCode.AUTH_ERROR)

    except requests.exceptions.RequestException as e:
        if debug_level >= 1:
            print(f"[debug] Connection error: {e}")
        print(f"Warning: Could not verify connection to {api_url}")


def _extract_host(url: str) -> str:
    """Extract user@host from URL for display."""
    from urllib.parse import urlparse  # ruff:ignore[import-outside-top-level]

    parsed = urlparse(url)
    host = parsed.hostname or url
    return f"root@{host}"


def _print_login_success(username: str, server_url: str, context_name: str) -> None:
    """
    One line: who, where, and under which name.

    All three matter and none was printed together before. "Which name" is the
    one a reader of `hop3 apps --context <?>` has to guess otherwise, and a
    server with several contexts gives no way to guess it. Anything that
    *changed* is announced separately, by the writer that changed it.
    """
    print(f"\nSigned in to {server_url} as {username}  (context {context_name!r})")
