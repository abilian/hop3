# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shell completion scripts for hop3 CLI.

Generates completion scripts for bash, zsh, and fish shells.
Supports dynamic command list refresh from the server.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter

# Cache file location
CACHE_DIR = Path.home() / ".cache" / "hop3"
COMMANDS_CACHE_FILE = CACHE_DIR / "commands.json"
COMMANDS_CACHE_TXT = CACHE_DIR / "commands.txt"  # Plain text for shell scripts
# Per ADR 036 M8.3: app names are cached alongside commands so shell
# completion (and the did-you-mean fallback) can suggest real apps without
# making a live RPC call on every TAB press.
APPS_CACHE_TXT = CACHE_DIR / "apps.txt"

# Static list of known commands (fallback when cache unavailable)
# These are embedded for static completion without server access
# Keep in sync with server commands (excluding hidden commands like git-hook)
FALLBACK_COMMANDS = [
    # Local commands (handled by CLI without server)
    "completion",
    "context",
    "init",
    "login",
    "settings",
    # Server commands - top-level
    "addons",
    "admin",
    "app",
    "apps",
    "auth",
    "backup",
    "config",
    "deploy",
    "help",
    "plugins",
    "ps",
    "run",
    "sbom",
    "system",
    "version",
    # Subcommands - addons
    "addons attach",
    "addons",
    "create",
    "addons",
    "destroy",
    "addons",
    "detach",
    "addons",
    "info",
    "addons",
    "list",
    "addons",
    "status",
    # Subcommands - admin
    "admin user add",
    "admin",
    "user",
    "disable",
    "admin",
    "user",
    "enable",
    "admin",
    "user",
    "generate-token",
    "admin",
    "user",
    "grant-admin",
    "admin",
    "user",
    "info",
    "admin",
    "user",
    "list",
    "admin",
    "user",
    "remove",
    "admin",
    "user",
    "revoke-admin",
    "admin",
    "user",
    "set-password",
    # Subcommands - app
    "app build-logs",
    "app",
    "debug",
    "app",
    "destroy",
    "app",
    "env",
    "app",
    "launch",
    "app",
    "logs",
    "app",
    "ping",
    "app",
    "restart",
    "app",
    "start",
    "app",
    "status",
    "app",
    "stop",
    # Subcommands - auth
    "auth login",
    "auth",
    "logout",
    "auth",
    "register",
    "auth",
    "whoami",
    # Subcommands - backup
    "backup create",
    "backup",
    "delete",
    "backup",
    "info",
    "backup",
    "list",
    "backup",
    "restore",
    # Subcommands - config
    "config get",
    "config",
    "live",
    "config",
    "migrate",
    "config",
    "set",
    "config",
    "show",
    "config",
    "unset",
    # Subcommands - ps
    "ps scale",
    # Subcommands - system
    "system check",
    "system",
    "cleanup",
    "system",
    "info",
    "system",
    "logs",
    "system",
    "ps",
    "system",
    "status",
    "system",
    "uptime",
]

# Local commands that are always added (not from server)
LOCAL_COMMANDS = [
    "completion",
    "context",
    "init",
    "login",
    "settings",
]

# Global flags that apply to all commands
GLOBAL_FLAGS = [
    "--help",
    "-h",
    "--json",
    "--quiet",
    "-y",
    "--yes",
    "--context",
    "-v",
    "-d",
    "--verbose",
    "--debug",
]

BASH_COMPLETION_SCRIPT = """# hop3 bash completion script
# Install: eval "$(hop3 completion bash)"
# Or: hop3 completion bash > /etc/bash_completion.d/hop3

_hop3_completions() {
    local cur prev words cword
    _init_completion -n : || return

    # Read commands from cache file if available, otherwise use fallback
    local cache_file="$HOME/.cache/hop3/commands.txt"
    local commands
    if [[ -f "$cache_file" ]]; then
        commands=$(tr '\\n' ' ' < "$cache_file")
    else
        commands="COMMANDS_PLACEHOLDER"
    fi

    local global_flags="FLAGS_PLACEHOLDER"

    # Handle flag completions
    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "$global_flags" -- "$cur"))
        return
    fi

    # Handle colon-separated subcommands
    if [[ "$cur" == *:* ]]; then
        local prefix="${cur%%:*}:"
        local subcommands=$(echo "$commands" | tr ' ' '\\n' | grep "^$prefix" | sort -u)
        COMPREPLY=($(compgen -W "$subcommands" -- "$cur"))
        __ltrim_colon_completions "$cur"
        return
    fi

    # If we're completing the first word, show top-level commands
    if [[ $cword -eq 1 ]]; then
        # Get unique top-level commands (before the colon)
        local top_level=$(echo "$commands" | tr ' ' '\\n' | sed 's/:.*$//' | sort -u)
        COMPREPLY=($(compgen -W "$top_level" -- "$cur"))
        return
    fi

    # For subsequent words, provide context-sensitive completion
    # (e.g., app names for app logs, etc.)
    # For now, just complete with known commands
    COMPREPLY=($(compgen -W "$commands" -- "$cur"))
}

# Register completion
complete -F _hop3_completions hop3
complete -F _hop3_completions hop
"""

ZSH_COMPLETION_SCRIPT = """#compdef hop3 hop

# hop3 zsh completion script
# Install: eval "$(hop3 completion zsh)"
# Or: hop3 completion zsh > ~/.zsh/completions/_hop3

_hop3() {
    local -a commands
    local -a global_flags
    local cache_file="$HOME/.cache/hop3/commands.txt"

    # Read commands from cache file if available, otherwise use fallback
    if [[ -f "$cache_file" ]]; then
        commands=("${(@f)$(< "$cache_file")}")
    else
        commands=(
COMMANDS_ZSH_PLACEHOLDER
        )
    fi

    global_flags=(
        '--help[Show help message]'
        '-h[Show help message]'
        '--json[Output in JSON format]'
        '--quiet[Suppress non-essential output]'
        '-y[Skip confirmation prompts]'
        '--yes[Skip confirmation prompts]'
        '--context[Use a specific context]:context name:'
        '-v[Verbose output]'
        '-d[Debug output]'
        '--verbose[Verbose output]'
        '--debug[Debug output]'
    )

    # Handle subcommand completion
    _arguments -C \\
        $global_flags \\
        '1: :->command' \\
        '*: :->args'

    case $state in
        command)
            _describe -t commands 'hop3 commands' commands
            ;;
        args)
            # Context-sensitive completion based on command
            case $words[2] in
                app logs|app status|app restart|app destroy|app:enable|app:disable)
                    # Could fetch app names dynamically here
                    _message 'app name'
                    ;;
                config get|config set|config unset)
                    _message 'variable name'
                    ;;
                *)
                    _describe -t commands 'hop3 commands' commands
                    ;;
            esac
            ;;
    esac
}

_hop3 "$@"
"""

FISH_COMPLETION_SCRIPT = """# hop3 fish completion script
# Install: hop3 completion fish > ~/.config/fish/completions/hop3.fish

# Disable file completion by default
complete -c hop3 -f
complete -c hop -f

# Global flags
complete -c hop3 -s h -l help -d 'Show help message'
complete -c hop -s h -l help -d 'Show help message'
complete -c hop3 -l json -d 'Output in JSON format'
complete -c hop -l json -d 'Output in JSON format'
complete -c hop3 -l quiet -d 'Suppress non-essential output'
complete -c hop -l quiet -d 'Suppress non-essential output'
complete -c hop3 -s y -l yes -d 'Skip confirmation prompts'
complete -c hop -s y -l yes -d 'Skip confirmation prompts'
complete -c hop3 -l context -d 'Use a specific context' -r
complete -c hop -l context -d 'Use a specific context' -r
complete -c hop3 -s v -l verbose -d 'Verbose output'
complete -c hop -s v -l verbose -d 'Verbose output'
complete -c hop3 -s d -l debug -d 'Debug output'
complete -c hop -s d -l debug -d 'Debug output'

# Function to get commands (from cache or fallback)
function __hop3_commands
    set -l cache_file "$HOME/.cache/hop3/commands.txt"
    if test -f "$cache_file"
        cat "$cache_file"
    else
        # Fallback commands
COMMANDS_FISH_FALLBACK
    end
end

# Commands completion
complete -c hop3 -n '__fish_use_subcommand' -a '(__hop3_commands)' -d 'hop3 command'
complete -c hop -n '__fish_use_subcommand' -a '(__hop3_commands)' -d 'hop3 command'
"""


def handle_completion(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Handle the completion command - output shell completion scripts."""
    if not args or args[0] in {"--help", "-h"}:
        print_completion_help()
        return

    # Handle --refresh flag
    if args[0] == "--refresh":
        refresh_commands_cache(config, printer)
        return

    # Handle --status flag
    if args[0] == "--status":
        show_cache_status()
        return

    shell = args[0].lower()

    if shell == "bash":
        print(generate_bash_completion())
    elif shell == "zsh":
        print(generate_zsh_completion())
    elif shell == "fish":
        print(generate_fish_completion())
    else:
        print(f"Unknown shell: {shell}", file=sys.stderr)
        print("Supported shells: bash, zsh, fish", file=sys.stderr)
        sys.exit(1)


def print_completion_help():
    """Print help for the completion command."""
    print("""Usage: hop3 completion <shell|option>

Generate shell completion scripts.

Shells:
  bash      Generate bash completion script
  zsh       Generate zsh completion script
  fish      Generate fish completion script

Options:
  --refresh   Fetch current commands from server and update cache
  --status    Show cache status (location, age, command count)

Installation:

  Bash (current session):
    eval "$(hop3 completion bash)"

  Bash (permanent):
    hop3 completion bash > /etc/bash_completion.d/hop3
    # Or for user-specific:
    hop3 completion bash >> ~/.bashrc

  Zsh (current session):
    eval "$(hop3 completion zsh)"

  Zsh (permanent):
    hop3 completion zsh > ~/.zsh/completions/_hop3
    # Make sure ~/.zsh/completions is in your fpath

  Fish:
    hop3 completion fish > ~/.config/fish/completions/hop3.fish

Keeping Completions Updated:

  The completion scripts read from a local cache file that can be
  updated from the server. No need to regenerate scripts after refresh:

    hop3 completion --refresh    # Fetch latest commands from server
    hop3 completion --status     # Check cache status

Examples:
  hop3 completion bash      # Output bash completion script
  hop3 completion --refresh # Update command cache from server
  hop3 completion --status  # Show cache info
""")


def get_commands() -> list[str]:
    """Get the list of commands, using cache if available.

    Priority:
    1. Cache file (if exists)
    2. Fallback to static list

    Returns:
        Sorted list of command names
    """
    # Try to read from cache
    cached = read_commands_cache()
    if cached:
        # Merge with local commands to ensure they're always present
        all_commands = set(cached) | set(LOCAL_COMMANDS)
        return sorted(all_commands)

    # Fall back to static list
    return sorted(FALLBACK_COMMANDS)


def read_commands_cache() -> list[str] | None:
    """Read commands from cache file.

    Returns:
        List of command names if cache exists and is valid, None otherwise
    """
    if not COMMANDS_CACHE_FILE.exists():
        return None

    try:
        data = json.loads(COMMANDS_CACHE_FILE.read_text())
        commands = data.get("commands", [])
        if isinstance(commands, list) and all(isinstance(c, str) for c in commands):
            return commands
    except (json.JSONDecodeError, OSError):
        pass

    return None


def write_commands_cache(commands: list[str]) -> None:
    """Write commands to cache files.

    Writes both JSON (with metadata) and plain text (for shell scripts).

    Args:
        commands: List of command names to cache
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    sorted_commands = sorted(commands)

    # Write JSON file with metadata
    data = {
        "commands": sorted_commands,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "version": 1,
    }
    COMMANDS_CACHE_FILE.write_text(json.dumps(data, indent=2))

    # Write plain text file for shell scripts (one command per line)
    COMMANDS_CACHE_TXT.write_text("\n".join(sorted_commands) + "\n")


def refresh_commands_cache(config: Config, printer: RichPrinter) -> None:
    """Fetch commands (and app names) from server and update the cache.

    Args:
        config: CLI configuration
        printer: Output printer
    """
    # Import here to avoid circular import
    from jsonrpcclient import Ok  # noqa: PLC0415

    from hop3_cli.rpc import Client  # noqa: PLC0415

    if not config.is_configured():
        print(
            "Error: CLI not configured. Run 'hop3 init' or 'hop3 context add' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Fetching commands from server...", file=sys.stderr)

    try:
        with Client(config=config) as client:
            response = client.rpc("cli", ["help", "commands"])

            if not isinstance(response, Ok):
                print("Error: Failed to fetch commands from server.", file=sys.stderr)
                sys.exit(1)

            result = response.result
            if not result or not isinstance(result, list):
                print("Error: Invalid response from server.", file=sys.stderr)
                sys.exit(1)

            # Extract commands from response
            # Response format: [{"t": "data", "data": {"commands": [...]}}]
            commands = None
            for item in result:
                if item.get("t") == "data" and "data" in item:
                    commands = item["data"].get("commands")
                    break

            if not commands:
                print("Error: No commands in server response.", file=sys.stderr)
                sys.exit(1)

            # Add local commands
            all_commands = sorted(set(commands) | set(LOCAL_COMMANDS))

            # Write to cache
            write_commands_cache(all_commands)

            print(
                f"✓ Cached {len(all_commands)} commands to {COMMANDS_CACHE_TXT}",
                file=sys.stderr,
            )

            # ADR 036 M8.3: also refresh the app-name cache. We do this in the
            # same invocation because it's what the user would expect from
            # "refresh completions" — both pools are stale at the same moments.
            # A failure to fetch apps doesn't fail the whole refresh: commands
            # already cached successfully and the apps cache is strictly extra.
            _refresh_apps_cache(client)

            print(
                "Your shell completions will now use the updated command list.",
                file=sys.stderr,
            )

    except Exception as e:
        print(f"Error connecting to server: {e}", file=sys.stderr)
        sys.exit(1)


def _refresh_apps_cache(client) -> None:
    """Fetch the app list and write names to APPS_CACHE_TXT.

    Non-fatal: if the fetch fails the commands cache still wrote. The app
    cache is only used by completion + did-you-mean, so stale is better
    than crashing the refresh.
    """
    from jsonrpcclient import Ok  # noqa: PLC0415

    try:
        resp = client.rpc("cli", ["app", "list"])
    except Exception as e:
        print(f"  (app cache: fetch failed: {e})", file=sys.stderr)
        return

    if not isinstance(resp, Ok) or not isinstance(resp.result, list):
        print("  (app cache: unexpected response)", file=sys.stderr)
        return

    apps: list[str] = []
    for item in resp.result:
        if item.get("t") == "table":
            rows = item.get("rows", [])
            for row in rows:
                if row and isinstance(row[0], str):
                    apps.append(row[0])

    if not apps:
        # Either no apps, or different response shape; don't trash an
        # existing cache with an empty file — skip instead.
        print("  (app cache: no apps found; cache unchanged)", file=sys.stderr)
        return

    write_apps_cache(sorted(set(apps)))
    print(f"✓ Cached {len(apps)} app name(s) to {APPS_CACHE_TXT}", file=sys.stderr)


def write_apps_cache(apps: list[str]) -> None:
    """Write the app name cache (plain text, one per line)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    APPS_CACHE_TXT.write_text("\n".join(apps) + "\n")


def read_apps_cache() -> list[str]:
    """Read cached app names; empty list if cache is missing or unreadable."""
    if not APPS_CACHE_TXT.is_file():
        return []
    try:
        return [
            line.strip()
            for line in APPS_CACHE_TXT.read_text().splitlines()
            if line.strip()
        ]
    except OSError:
        return []


def show_cache_status() -> None:
    """Show the status of the commands cache."""
    if not COMMANDS_CACHE_TXT.exists():
        print("Cache status: Not found")
        print(f"Cache location: {COMMANDS_CACHE_TXT}")
        print(f"Using: Static fallback list ({len(FALLBACK_COMMANDS)} commands)")
        print("\nTo create cache, run: hop3 completion --refresh")
        return

    try:
        data = json.loads(COMMANDS_CACHE_FILE.read_text())
        commands = data.get("commands", [])
        updated_at = data.get("updated_at", "unknown")

        # Calculate age
        try:
            cache_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - cache_time
            age_str = _format_age(age)
        except Exception:
            age_str = "unknown"

        print("Cache status: Found")
        print(f"Cache location: {COMMANDS_CACHE_TXT}")
        print(f"Commands cached: {len(commands)}")
        print(f"Last updated: {updated_at}")
        print(f"Age: {age_str}")
        print("\nShell completions automatically use this cache.")
        print("To refresh, run: hop3 completion --refresh")

    except Exception as e:
        print(f"Cache status: Error reading cache ({e})")
        print(f"Cache location: {COMMANDS_CACHE_TXT}")


def _format_age(age) -> str:
    """Format a timedelta as a human-readable age string."""
    total_seconds = int(age.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds} seconds"
    if total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    if total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"

    days = total_seconds // 86400
    return f"{days} day{'s' if days != 1 else ''}"


def generate_bash_completion() -> str:
    """Generate bash completion script."""
    commands = get_commands()
    commands_str = " ".join(commands)
    flags_str = " ".join(GLOBAL_FLAGS)

    script = BASH_COMPLETION_SCRIPT
    script = script.replace("COMMANDS_PLACEHOLDER", commands_str)
    script = script.replace("FLAGS_PLACEHOLDER", flags_str)
    return script


def generate_zsh_completion() -> str:
    """Generate zsh completion script."""
    commands = get_commands()

    # Format commands as zsh array with descriptions
    command_lines = []
    for cmd in commands:
        # For now, use the command name as the description
        # Could enhance with actual descriptions later
        desc = cmd.replace(":", " ")  # Simple description
        command_lines.append(f"        '{cmd}:{desc}'")

    commands_zsh = "\n".join(command_lines)
    script = ZSH_COMPLETION_SCRIPT.replace("COMMANDS_ZSH_PLACEHOLDER", commands_zsh)
    return script


def generate_fish_completion() -> str:
    """Generate fish completion script."""
    # Use fallback commands for the embedded list
    # (cache will be read at runtime if available)
    commands = sorted(FALLBACK_COMMANDS)

    # Generate fish echo commands for fallback
    command_lines = []
    for cmd in commands:
        command_lines.append(f"        echo '{cmd}'")

    commands_fish = "\n".join(command_lines)
    script = FISH_COMPLETION_SCRIPT.replace("COMMANDS_FISH_FALLBACK", commands_fish)
    return script
