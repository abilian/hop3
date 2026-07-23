# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Login command - authenticate to a Hop3 server."""

from __future__ import annotations

import getpass
import os
import sys
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from jsonrpcclient import Error, Ok

from hop3_cli.tokens import extract_jwt

from .help_text import print_login_help
from .ssh_ops import (
    BootstrapError,
    get_magic_link_via_ssh,
    get_ssh_token,
    get_token_via_ssh,
    infer_web_url,
)

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_login(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Handle the login command.

    Supports multiple authentication methods:
    - URL with token: http://server:port?token=eyJ... (easiest for local dev)
    - --ssh user@server: SSH-based authentication (for remote servers)
    - --token <token>: Use a pre-generated token with separate --url
    - (default): Username/password authentication via the server API

    Usage:
        hop3 login "http://localhost:8000?token=eyJ..."  # URL with embedded token
        hop3 login --ssh user@server                     # SSH-based auth
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

    # Dispatch based on authentication method
    if "--web" in args:
        handle_login_web(args, config, printer)
    elif "--ssh" in args:
        handle_login_ssh(args, config, printer)
    elif "--token" in args:
        handle_login_token(args, config, printer)
    else:
        # Default: password-based authentication
        handle_login_password(args, config, printer)


def handle_logout(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Log out: revoke the token on the server and clear it locally.

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
    """Handle password-based login via the server API.

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

    print("Server not configured.", file=sys.stderr)
    print("\nTo configure, use one of:", file=sys.stderr)
    print(
        "  hop3 init --ssh root@your-server.com  # First-time setup",
        file=sys.stderr,
    )
    print(
        "  hop3 login --ssh root@your-server.com # If you have SSH access",
        file=sys.stderr,
    )
    print("  hop3 settings set server https://your-server.com", file=sys.stderr)
    sys.exit(1)


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
    response, username: str, config: Config, printer: RichPrinter
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
                        "Error: No server configured. Use 'hop3 init' or 'hop3 login --ssh' first.",
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
        case _:
            print("Unexpected response from server", file=sys.stderr)
            sys.exit(1)


def _extract_token_from_login_response(result: list[dict]) -> str | None:
    """Extract the JWT token from the `auth get-token` response.

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
    """Handle --web flag to generate a magic link for browser login.

    This generates a short-lived, single-use URL that can be used to log into
    the web dashboard without entering a password. Requires SSH access.

    Usage:
        hop3 login --web                    # Uses current context
        hop3 login --web server.com         # SSH as root@server.com
        hop3 login --web user@server.com    # SSH as user@server.com
    """
    ssh_target, username = _parse_login_web_args(args, config)

    print(f"\nConnecting to {ssh_target}...")

    try:
        result = get_magic_link_via_ssh(ssh_target, username)
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # The server returns a full URL when it has a public admin domain (it knows
    # its own scheme/host then). Otherwise it returns a bare token and we point
    # the browser at the app's HTTP port directly — without an admin domain the
    # dashboard isn't fronted by nginx/TLS on 443 (that path 404s).
    if result.startswith(("http://", "https://")):
        magic_link = result
    else:
        magic_link = f"{infer_web_url(ssh_target)}/auth/magic/{result}"

    print()
    print("Magic link generated!")
    print()
    print("Open this URL in your browser to log in:")
    print()
    print(f"  {magic_link}")
    print()
    print("Note: This link expires in 5 minutes and can only be used once.")


def _parse_login_web_args(args: list[str], config: Config) -> tuple[str, str]:
    """Parse arguments for login --web command.

    Returns:
        Tuple of (ssh_target, username)
    """
    ssh_target = None
    username = "admin"  # Default to admin user

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--web" and i + 1 < len(args):
            # Next argument should be the SSH target
            next_arg = args[i + 1]
            if not next_arg.startswith("-"):
                ssh_target = next_arg
                i += 2
            else:
                i += 1
        elif arg == "--web":
            # --web without argument - will use context
            i += 1
        elif arg == "--username" and i + 1 < len(args):
            username = args[i + 1]
            i += 2
        elif not arg.startswith("-") and not ssh_target:
            # Positional argument could be SSH target
            ssh_target = arg
            i += 1
        else:
            i += 1

    # If no SSH target provided, try to get it from the current context
    if not ssh_target:
        ssh_target = _get_ssh_target_from_config(config)

    if not ssh_target:
        print("Error: No server configured.", file=sys.stderr)
        print("\nUse one of:", file=sys.stderr)
        print("  hop3 login --web root@server.com  # Specify server", file=sys.stderr)
        print(
            "  hop3 login --ssh root@server.com  # Configure context first",
            file=sys.stderr,
        )
        sys.exit(1)

    # Ensure SSH target has user@ prefix (default to root)
    if "@" not in ssh_target:
        ssh_target = f"root@{ssh_target}"

    return ssh_target, username


def _get_ssh_target_from_config(config: Config) -> str | None:
    """Extract SSH target from the current context's API URL.

    Handles both SSH URLs (ssh://root@host) and HTTP URLs (https://host).
    """
    api_url = config.get_api_url()
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


def record_server_login(config: Config, server_url: str, token: str) -> None:
    """ADR 042: stash the token + set this server as the default target.

    This is the *only* place a login persists credentials: the token goes to the
    per-server credential store (keyed by canonical address); config.toml stays
    secret-free. When the user named the login with ``--context <name>``, the
    server is recorded as that **global context** (so `--context <name>` selects
    it project-lessly) and becomes the default context. Otherwise it sets the
    unnamed default server. Either way the change is surfaced, so a login never
    silently retargets `hop3 apps` & friends.
    """
    if not server_url:
        return
    from hop3_cli.core import credential_store  # ruff:ignore[import-outside-top-level]

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

    context_name = config.get_context_override()
    if context_name:
        config.set_context_server(context_name, server_url)
        previous = config.get_default_context()
        config.set_default_context(context_name)
        if previous != context_name:
            print(f"  context {context_name!r} -> {server_url} (now the default)")
        return

    previous = config.get_default_server()
    config.set_default_server(server_url)
    if previous != server_url:
        print(f"  default server is now {server_url}")


def handle_login_token(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Handle token-based login for local development or automation.

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


def _resolve_server_url(server_url: str | None, config) -> str:
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
    """Verify token by calling auth whoami on the server.

    Returns:
        Username if successful, None if verification failed
    """
    # Import here to avoid circular import
    from hop3_cli.config import (  # ruff:ignore[import-outside-top-level]
        Config as TempConfig,
    )
    from hop3_cli.rpc import Client  # ruff:ignore[import-outside-top-level]

    # Create a temporary config for verification. Must use the nested
    # [contexts.*] shape — Config.get_api_url() no longer reads a flat
    # top-level "api_url" key (removed in the context-model refactor), so a
    # flat dict here yields api_url=None and Client raises CliError, which
    # the broad except below misreports as "Could not connect". That made
    # token-based `hop3 login "<url>?token=..."` fail even against a healthy
    # server (e.g. the Docker demo login on localhost:18000).
    temp_config = TempConfig(
        data={
            "contexts": {"default": {"api_url": server_url, "api_token": token}},
            "current_context": "default",
        },
        config_file=None,
    )

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
                case _:
                    print("Unexpected response from server", file=sys.stderr)
                    return None

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
) -> str:
    """Determine the API URL to record for this login.

    Returns the connection address: the explicit ``--url`` (verified for HTTPS,
    aborting on an untrusted cert) or an SSH-tunnel URL built from the target.
    """
    if api_url:
        # User explicitly provided URL - use HTTP API
        if debug_level >= 1:
            print(f"[debug] Will use HTTP API at: {api_url}")
        # For HTTPS, verify the connection works with system CA bundle
        # (aborts the login on an untrusted certificate).
        if api_url.startswith("https://"):
            config_data = {"api_url": api_url, "api_token": token}
            _verify_https_connection(api_url, token, config, config_data, debug_level)
        return api_url

    # Default: use SSH tunnel for all subsequent commands
    save_url = _build_ssh_url(ssh_target)
    if debug_level >= 1:
        print(f"[debug] Will use SSH tunnel: {save_url}")
    return save_url


def handle_login_ssh(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Handle the login --ssh command for getting token via SSH.

    SSH access is the authentication - no username/password needed by default.
    If --username is provided, uses the legacy flow for that specific user.

    Usage:
        hop3 login --ssh user@server                    # Auto-auth (recommended)
        hop3 login --ssh user@server --username admin   # Specific user (legacy)
        hop3 login --ssh user@server --url https://...  # Use HTTP API instead
        hop3 login --ssh user@server -d                 # Show debug info
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
    save_url = _determine_save_url(api_url, ssh_target, token, config, debug_level)

    record_server_login(config, save_url, token)
    if debug_level >= 1:
        print(f"[debug] Token stored for: {save_url}")

    _print_login_success(display_username, save_url)


def _build_ssh_url(ssh_target: str) -> str:
    """Build SSH URL from SSH target.

    Args:
        ssh_target: SSH target (user@host or host)

    Returns:
        SSH URL for the API (e.g., ssh://root@hop3.dev)
    """
    if "@" in ssh_target:
        return f"ssh://{ssh_target}"
    return f"ssh://root@{ssh_target}"


def _parse_login_ssh_args(args: list[str]) -> tuple[str, str | None, str | None, int]:
    """Parse arguments for login --ssh command.

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

    if not ssh_target:
        print_login_help()
        print(
            "\nError: --ssh requires a target (e.g., root@server.com)", file=sys.stderr
        )
        sys.exit(1)

    # Type narrowing: ssh_target is str after the check above
    assert ssh_target is not None

    return ssh_target, username, api_url, debug_level


def _verify_https_connection(
    api_url: str,
    token: str,
    config: Config,
    config_data: dict,
    debug_level: int = 0,
) -> None:
    """Verify HTTPS connection works with the system CA bundle.

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
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
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
            f"       hop3 login --ssh {host}\n"
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


def _print_login_success(username: str, server_url: str) -> None:
    """Print success message after login."""
    print(f"\nToken generated for user '{username}'")
    print(f"Token stored for {server_url}")
    print("\nWelcome back! Try:")
    print("  hop3 apps           # List applications")
    print("  hop3 auth whoami    # Check current user")
