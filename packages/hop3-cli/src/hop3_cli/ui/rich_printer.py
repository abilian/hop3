# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Enhanced printer with Rich formatting support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

Message = list[dict[str, Any]]


@dataclass(frozen=True)
class RichPrinter:
    """Enhanced printer with Rich formatting, colors, and progress indicators."""

    verbose: bool = False
    quiet: bool = False
    json_output: bool = False
    debug: bool = False

    def __post_init__(self):
        """Initialize console after dataclass creation."""
        object.__setattr__(self, "_console", Console(stderr=False))
        object.__setattr__(self, "_console_err", Console(stderr=True))
        object.__setattr__(self, "_json_buffer", [])

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
        return self._console  # type: ignore

    @property
    def console_err(self) -> Console:
        """Get the Rich stderr console instance."""
        return self._console_err  # type: ignore

    @property
    def json_buffer(self) -> list[dict]:
        """Get the JSON output buffer."""
        return self._json_buffer  # type: ignore

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
        """Print plain text."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = obj.get("text", "")
        self.console.print(text)

    def print_error(self, obj: dict) -> None:
        """Print error messages in red."""
        # Always print errors, even in quiet mode
        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = obj.get("text", "")
        self.console_err.print(f"[bold red]ERROR:[/bold red] {text}")

    def print_success(self, obj: dict) -> None:
        """Print success messages in green."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = obj.get("text", "")
        self.console.print(f"[bold green]✓[/bold green] {text}")

    def print_warning(self, obj: dict) -> None:
        """Print warning messages in yellow."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = obj.get("text", "")
        self.console.print(f"[bold yellow]⚠[/bold yellow] {text}")

    def print_info(self, obj: dict) -> None:
        """Print info messages in blue."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = obj.get("text", "")
        self.console.print(f"[bold blue]i[/bold blue] {text}")

    def print_progress(self, obj: dict) -> None:
        """Print progress indicator."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = obj.get("text", "")
        # For now, just print with a spinner emoji
        # TODO: Implement real progress bar for long operations
        self.console.print(f"[cyan]⏳[/cyan] {text}")

    def print_log(self, obj: dict) -> None:
        """Print deployment log entry with appropriate color and verbosity filtering.

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

        if style:
            self.console.print(f"[{style}]{msg}[/{style}]")
        else:
            self.console.print(msg)

    def print_panel(self, obj: dict) -> None:
        """Print text in a panel/box."""
        if self.quiet:
            return

        if self.json_output:
            self.json_buffer.append(obj)
            return

        text = obj.get("text", "")
        title = obj.get("title")
        style = obj.get("style", "cyan")

        panel = Panel(text, title=title, border_style=style)
        self.console.print(panel)

    def confirm(self, message: str, *, default: bool = False) -> bool:
        """Ask for user confirmation.

        Args:
            message: The confirmation message
            default: Default value if user just presses Enter

        Returns:
            True if user confirmed, False otherwise
        """
        if self.json_output:
            # In JSON mode, auto-confirm (assume -y flag)
            return True

        prompt = f"{message} [y/N]: " if not default else f"{message} [Y/n]: "
        response = input(prompt).strip().lower()

        if not response:
            return default

        return response in {"y", "yes"}
