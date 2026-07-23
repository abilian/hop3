# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Enhanced printer with Rich formatting support."""

from __future__ import annotations

import base64
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.markup import escape as rich_escape
from rich.table import Table

Message = list[dict[str, Any]]


@dataclass(frozen=True)
class RichPrinter:
    """Enhanced printer with Rich formatting, colors, and progress indicators."""

    verbose: bool = False
    quiet: bool = False
    json_output: bool = False
    debug: bool = False
    # Internal fields initialized in __post_init__
    _console: Console = field(init=False, repr=False, compare=False)
    _console_err: Console = field(init=False, repr=False, compare=False)
    _json_buffer: list[dict[str, Any]] = field(init=False, repr=False, compare=False)
    # ADR 036 D19c: current context/app used to build the [ctx / app] prefix
    # for summary lines. Populated by set_scope() after resolution.
    _scope: dict[str, str | None] = field(init=False, repr=False, compare=False)
    # The --context/--app the user actually TYPED, used to render `hint` items
    # (follow-up suggestions) in the user's own dialect. Populated by
    # set_suggestion_selectors().
    _suggest: dict[str, str | None] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Initialize console after dataclass creation."""
        object.__setattr__(self, "_console", Console(stderr=False))
        object.__setattr__(self, "_console_err", Console(stderr=True))
        object.__setattr__(self, "_json_buffer", [])
        object.__setattr__(self, "_scope", {"context": None, "app": None})
        object.__setattr__(self, "_suggest", {"context": None, "app": None})

    def set_scope(self, *, context: str | None, app: str | None) -> None:
        """
        Set the active context/app used to prefix summary lines (ADR 036 D19c).

        Called by the main dispatch once the effective context and app are
        known (post alias expansion and app resolution). Safe to call with
        None values — the prefix simply omits the missing side.
        """
        self._scope["context"] = context
        self._scope["app"] = app

    def set_suggestion_selectors(self, *, context: str | None, app: str | None) -> None:
        """
        Record the ``--context``/``--app`` the user actually TYPED.

        Follow-up suggestions (``hint`` items) reproduce these verbatim so a
        copy-pasted next command lands on the same target. Typed — not resolved:
        if the user relied on implicit app/context resolution, the suggestion
        omits the flag and resolves the same way on the next run.
        """
        self._suggest["context"] = context
        self._suggest["app"] = app

    @property
    def verbosity(self) -> int:
        """Get verbosity level as integer."""
        if self.quiet:
            return 0
        if self.debug:
            return 3
        if self.verbose:
            return 2
        return 1

    @property
    def console(self) -> Console:
        """Get the Rich console instance."""
        return self._console

    @property
    def console_err(self) -> Console:
        """Get the Rich stderr console instance."""
        return self._console_err

    @property
    def json_buffer(self) -> list[dict[str, Any]]:
        """Get the JSON output buffer."""
        return self._json_buffer

    def print(self, msg: Message) -> None:
        """Print a message using appropriate formatting."""
        if self.json_output:
            # Collect all messages for JSON output
            for item in msg:
                self.json_buffer.append(item)
            return

        for item in msg:
            t = item.get("t", "text")
            meth = getattr(self, f"print_{t}", self.print_text)
            meth(item)

    def flush_json(self) -> None:
        """Flush collected JSON output."""
        if self.json_output:
            print(json.dumps(self.json_buffer, indent=2))

    def print_table(self, table_data: dict) -> None:
        """Print a table using Rich Table."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(table_data)
            return

        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])

        table = Table(show_header=True, header_style="bold cyan")
        for header in headers:
            table.add_column(header)

        for row in rows:
            # Convert all items to strings
            str_row = [str(item) if item is not None else "" for item in row]
            table.add_row(*str_row)

        self.console.print(table)

    def print_text(self, obj: dict) -> None:
        """
        Print plain text.

        ``markup=False`` is essential: server text is literal and routinely
        contains square brackets that are NOT Rich markup — e.g. the
        ``[top]`` / ``[addon]`` markers in ``hop help --all`` and ``[options]``
        / ``[aliases]`` / ``[current]`` in command help. With markup enabled
        Rich would parse those as style tags and silently strip them, mangling
        the output.
        """
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = obj.get("text", "")
        # soft_wrap=True: without it Rich word-wraps at the console width (80
        # when stdout is piped/not a TTY), injecting hard newlines mid-string.
        # That corrupts machine-consumable single-line values — most visibly
        # `hop3 auth get-token` (built for TOKEN=$(...)), whose JWT would be
        # split across lines. Soft wrap emits the literal text; a TTY still
        # wraps visually.
        self.console.print(text, markup=False, highlight=False, soft_wrap=True)

    def print_hint(self, obj: dict) -> None:
        """
        Render a follow-up-command suggestion in the user's own dialect.

        The server provides the bare verb (``command``, no target flags) and a
        ``message`` carrying a ``{cmd}`` placeholder. We fill the placeholder
        with ``hop3 <command>`` plus the ``--context``/``--app`` the user typed,
        so a copy-paste targets the same context the user is already on.
        """
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        cmd = self._render_suggested_command(obj.get("command", ""))
        # "{cmd}" is a literal placeholder in the server-supplied message, not an
        # f-string — the command is substituted in here, CLI-side.
        message = obj.get("message", "").replace("{cmd}", f"'{cmd}'")
        self.console.print(message, markup=False, highlight=False)

    def _render_suggested_command(self, command: str) -> str:
        """Build ``hop3 <command>`` + the typed --context/--app selectors."""
        parts = ["hop3", command]
        ctx = self._suggest.get("context")
        app = self._suggest.get("app")
        if ctx:
            parts.append(f"--context {ctx}")
        if app:
            parts.append(f"--app {app}")
        return " ".join(p for p in parts if p)

    def print_blob(self, obj: dict) -> None:
        """
        Write a base64 blob's bytes verbatim to stdout.

        Used by `addon <type> export` to stream a dump to the client; the bytes
        go to stdout (redirect to a file) while status/summary go to stderr.
        Always emitted (even in quiet mode) — the blob IS the requested output.
        """
        if self.json_output:
            self.json_buffer.append(obj)
            return

        sys.stdout.buffer.write(base64.b64decode(obj.get("data", "")))
        sys.stdout.flush()

    def print_error(self, obj: dict) -> None:
        """Print error messages in red."""
        # Always print errors, even in quiet mode
        if self.json_output:
            self.json_buffer.append(obj)
            return

        # Escape the server-supplied text: it routinely contains brackets that
        # are NOT Rich markup (e.g. MSBuild appends "[/path/app.csproj]" to
        # every diagnostic). Unescaped, Rich raises a MarkupError that masks the
        # real failure. Only the static prefix carries markup.
        text = rich_escape(obj.get("text", ""))
        self.console_err.print(f"[bold red]ERROR:[/bold red] {text}")

    def print_success(self, obj: dict) -> None:
        """Print success messages in green."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = rich_escape(obj.get("text", ""))
        self.console.print(f"[bold green]✓[/bold green] {text}")

    def print_warning(self, obj: dict) -> None:
        """
        Print warning messages in yellow.

        Routed to stderr per ADR 036 D19: warnings are status, not data;
        keeping them off stdout means ``hop3 cmd | grep`` doesn't see them.
        """
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = rich_escape(obj.get("text", ""))
        self.console_err.print(f"[bold yellow]⚠[/bold yellow] {text}")

    def print_info(self, obj: dict) -> None:
        """Print info messages in blue (stderr per ADR 036 D19)."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = rich_escape(obj.get("text", ""))
        self.console_err.print(f"[bold blue]i[/bold blue] {text}")

    def print_progress(self, obj: dict) -> None:
        """Print progress indicator (stderr per ADR 036 D19)."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = rich_escape(obj.get("text", ""))
        # For now, just print with a spinner emoji
        # TODO: Implement real progress bar for long operations
        self.console_err.print(f"[cyan]⏳[/cyan] {text}")

    def print_log(self, obj: dict) -> None:
        """
        Print deployment log entry with appropriate color and verbosity filtering.

        Log levels:
            0 = important (always shown unless quiet)
            1 = normal (shown by default)
            2 = verbose (shown with -v)
            3 = debug (shown with --debug)
        """
        if self.json_output:
            self.json_buffer.append(obj)
            return

        msg = obj.get("msg", "")
        level = obj.get("level", 0)
        fg = obj.get("fg", "")

        # Filter based on verbosity
        if level > self.verbosity:
            return

        # Map server colors to Rich styles
        style_map = {
            "green": "green",
            "red": "red",
            "blue": "cyan",
            "yellow": "yellow",
            "cyan": "cyan",
            "magenta": "magenta",
        }
        style = style_map.get(fg, "")

        # Escape Rich markup in log messages to prevent parsing errors
        # (app logs often contain brackets like [2025-01-15] or [database])
        escaped_msg = rich_escape(msg)

        if style:
            self.console.print(f"[{style}]{escaped_msg}[/{style}]")
        else:
            self.console.print(escaped_msg)

    def print_data(self, obj: dict) -> None:
        """
        Print structured data (typically for JSON output mode or programmatic use).

        In normal mode, data is displayed as formatted JSON.
        In JSON output mode, it's added to the buffer as-is.
        """
        if self.json_output:
            self.json_buffer.append(obj)
            return

        # In normal mode, pretty-print the data payload
        data = obj.get("data", {})
        self.console.print(json.dumps(data, indent=2))

    def print_summary(self, obj: dict) -> None:
        """
        Print a state-change summary line (ADR 036 D19c).

        Summaries are the one-or-two-line confirmation a mutating command
        prints after it succeeds ("set FOO=bar; restarted web worker.").
        Routed to stderr so ``hop3 cmd | grep`` pipelines stay clean, with
        a ``[context / app]`` prefix so the user can see at a glance where
        the change landed.
        """
        if self.json_output:
            self.json_buffer.append(obj)
            return

        # Summaries survive --quiet: they're the one signal a script might
        # scrape to confirm "the thing actually happened". If this turns out
        # to be too noisy in practice, tighten later.
        text = obj.get("text", "")
        ctx = self._scope.get("context")
        app = self._scope.get("app")
        if ctx and app:
            prefix = f"[{ctx} / {app}]"
        elif ctx:
            prefix = f"[{ctx}]"
        elif app:
            prefix = f"[{app}]"
        else:
            prefix = ""
        line = f"{prefix} {text}".strip() if prefix else text
        # Escape Rich markup so the brackets in the prefix and any user
        # text aren't reinterpreted as style tags.
        self.console_err.print(rich_escape(line))

    def print_debug(self, message: str, min_level: int = 2) -> None:
        """
        Print debug message if verbosity is high enough.

        Args:
            message: Debug message to print
            min_level: Minimum verbosity level required (2=with -d, 3=with -dd)
        """
        if self.verbosity < min_level:
            return

        if self.json_output:
            self.json_buffer.append({"t": "debug", "text": message})
            return

        self.console.print(f"[dim][debug][/dim] {message}")
