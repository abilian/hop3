# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Chat/command interface screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.events import Key
from textual.screen import Screen
from textual.suggester import Suggester
from textual.widgets import Footer, Header, Input, Static

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI


# Available commands for completion
COMMANDS = [
    "apps",
    "app",
    "start",
    "stop",
    "restart",
    "logs",
    "env",
    "status",
    "clear",
    "help",
    "deploy",
    "backup",
    "restore",
]


class CommandSuggester(Suggester):
    """Provides command suggestions for the chat input."""

    def __init__(self, app_names: list[str] | None = None) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self._app_names: list[str] = app_names or []

    def update_app_names(self, app_names: list[str]) -> None:
        """Update the list of known app names for completion."""
        self._app_names = app_names

    async def get_suggestion(self, value: str) -> str | None:
        """Get a suggestion for the current input."""
        if not value:
            return None

        parts = value.split()

        # If typing first word, suggest commands
        if len(parts) == 1:
            prefix = parts[0].lower()
            for cmd in COMMANDS:
                if cmd.startswith(prefix) and cmd != prefix:
                    return cmd
            return None

        # If typing second word after app-related commands, suggest app names
        if len(parts) == 2:
            cmd = parts[0].lower()
            if cmd in {
                "app",
                "start",
                "stop",
                "restart",
                "logs",
                "env",
                "deploy",
                "backup",
            }:
                prefix = parts[1].lower()
                for app_name in self._app_names:
                    if app_name.lower().startswith(prefix) and app_name != parts[1]:
                        return f"{parts[0]} {app_name}"
                return None

        return None


class ChatMessage(Static):
    """A single chat message."""

    def __init__(
        self,
        content: str,
        *,
        is_user: bool = True,
        is_error: bool = False,
    ) -> None:
        super().__init__()
        self.content = content
        self.is_user = is_user
        self.is_error = is_error

    def compose(self) -> ComposeResult:
        if self.is_user:
            yield Static(f"[bold]>[/bold] {self.content}", classes="user-message")
        elif self.is_error:
            yield Static(f"[red]{self.content}[/]", classes="error-message")
        else:
            yield Static(self.content, classes="system-message")


class ChatScreen(Screen):
    """Screen for chat/command interface."""

    CSS = """
    ChatScreen {
        layout: vertical;
    }

    #chat-container {
        height: 1fr;
        padding: 1;
    }

    #chat-messages {
        height: auto;
    }

    .user-message {
        margin-bottom: 1;
    }

    .system-message {
        margin-bottom: 1;
        padding-left: 2;
    }

    .error-message {
        margin-bottom: 1;
        padding-left: 2;
    }

    #input-bar {
        dock: bottom;
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    #command-input {
        width: 100%;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Command history
        self._history: list[str] = []
        self._history_index: int = 0
        # Track chat content
        self._chat_content: str = ""
        # Command suggester for tab completion
        self._suggester = CommandSuggester()

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return self.app  # type: ignore[return-value]
        return None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="chat-container"):
            yield Static(id="chat-messages")
        with Static(id="input-bar"):
            yield Input(
                placeholder="Type command or ? for help (Tab to complete)",
                id="command-input",
                suggester=self._suggester,
            )
        yield Footer()

    def on_mount(self) -> None:
        """Set up the chat interface."""
        self._add_system_message(
            "Welcome to Hop3 Command Interface\nType a command or ? for help\nPress Tab to auto-complete"
        )
        self.query_one("#command-input", Input).focus()
        # Load app names for completion
        self._load_app_names()

    def _load_app_names(self) -> None:
        """Load app names for tab completion."""
        self.run_worker(self._fetch_app_names(), exclusive=True)

    async def _fetch_app_names(self) -> None:
        """Fetch app names from server."""
        if not self.hop3_app:
            # Use mock app names for testing
            self._suggester.update_app_names([
                "myapp",
                "api-server",
                "worker",
                "frontend",
                "broken-app",
            ])
            return

        try:
            apps = await self.hop3_app.api_client.list_apps()
            app_names = [app.name for app in apps]
            self._suggester.update_app_names(app_names)
        except Exception:
            # Silently fail - completion just won't have app names
            pass

    def _add_user_message(self, content: str) -> None:
        """Add a user message to the chat."""
        messages = self.query_one("#chat-messages", Static)
        self._chat_content = f"{self._chat_content}\n[bold]>[/bold] {content}"
        messages.update(self._chat_content)
        self._scroll_to_bottom()

    def _add_system_message(self, content: str) -> None:
        """Add a system message to the chat."""
        messages = self.query_one("#chat-messages", Static)
        if self._chat_content:
            self._chat_content = f"{self._chat_content}\n\n{content}"
        else:
            self._chat_content = content
        messages.update(self._chat_content)
        self._scroll_to_bottom()

    def _add_error_message(self, content: str) -> None:
        """Add an error message to the chat."""
        messages = self.query_one("#chat-messages", Static)
        self._chat_content = f"{self._chat_content}\n\n[red]{content}[/]"
        messages.update(self._chat_content)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        """Scroll chat to bottom."""
        container = self.query_one("#chat-container", VerticalScroll)
        container.scroll_end(animate=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command submission."""
        if event.input.id != "command-input":
            return

        command = event.value.strip()
        if not command:
            return

        # Add to history
        self._history.append(command)
        self._history_index = len(self._history)

        # Clear input
        event.input.value = ""

        # Show user command
        self._add_user_message(command)

        # Process command
        self._process_command(command)

    def _process_command(self, command: str) -> None:
        """Process a command and show output."""
        parts = command.split()
        cmd = parts[0].lower() if parts else ""
        args = parts[1:] if len(parts) > 1 else []

        # Commands that don't require arguments
        simple_commands = {
            "?": self._show_help,
            "help": self._show_help,
            "apps": self._cmd_apps,
            "status": self._cmd_status,
            "clear": self._cmd_clear,
        }

        # Commands that require an app name argument
        app_commands = {
            "app": (self._cmd_app_detail, "app <name>"),
            "start": (self._cmd_start, "start <app_name>"),
            "stop": (self._cmd_stop, "stop <app_name>"),
            "restart": (self._cmd_restart, "restart <app_name>"),
            "logs": (self._cmd_logs, "logs <app_name>"),
        }

        if cmd in simple_commands:
            simple_commands[cmd]()
        elif cmd in app_commands:
            handler, usage = app_commands[cmd]
            if args:
                handler(args[0])
            else:
                self._add_error_message(f"Usage: {usage}")
        else:
            self._add_error_message(f"Unknown command: {cmd}\nType ? for help")

    def _show_help(self) -> None:
        """Show help message."""
        self._add_system_message(
            "[bold]Available Commands[/bold]\n"
            "─────────────────────\n"
            "apps                List all applications\n"
            "app <name>          Show app details\n"
            "start <name>        Start application\n"
            "stop <name>         Stop application\n"
            "restart <name>      Restart application\n"
            "logs <name>         View app logs\n"
            "status              System status\n"
            "clear               Clear chat\n"
            "help, ?             Show this help"
        )

    def _cmd_apps(self) -> None:
        """List applications."""
        # TODO: Fetch from API
        self._add_system_message(
            "[bold]Applications[/bold]\n"
            "─────────────────────\n"
            "[green]●[/] myapp        RUNNING  :8000\n"
            "[green]●[/] api-server   RUNNING  :8001\n"
            "[dim]○[/] worker       STOPPED\n"
            "[green]●[/] frontend     RUNNING  :8002\n"
            "[red]●[/] broken-app   FAILED"
        )

    def _cmd_app_detail(self, name: str) -> None:
        """Show app details."""
        # TODO: Fetch from API
        self._add_system_message(
            f"[bold]{name}[/bold]\n"
            "─────────────────────\n"
            "Status:   [green]RUNNING[/]\n"
            "Port:     8000\n"
            "Runtime:  uwsgi\n"
            "Workers:  2\n"
            f"URL:      https://{name}.example.com"
        )

    def _cmd_start(self, name: str) -> None:
        """Start an application."""
        self._add_system_message(f"Starting {name}...")
        # TODO: Call API
        self._add_system_message(f"[green]✓[/] {name} started successfully")

    def _cmd_stop(self, name: str) -> None:
        """Stop an application."""
        self._add_system_message(f"Stopping {name}...")
        # TODO: Call API
        self._add_system_message(f"[green]✓[/] {name} stopped")

    def _cmd_restart(self, name: str) -> None:
        """Restart an application."""
        self._add_system_message(f"Restarting {name}...")
        # TODO: Call API
        self._add_system_message(f"[green]✓[/] {name} restarted successfully")

    def _cmd_logs(self, name: str) -> None:
        """Show recent logs."""
        # TODO: Fetch from API
        self._add_system_message(
            f"[bold]Recent logs for {name}[/bold]\n"
            "─────────────────────\n"
            "10:32:15 [INFO]  Request processed in 45ms\n"
            "10:32:14 [INFO]  GET /api/users 200\n"
            "10:32:10 [INFO]  Database query completed\n"
            "\n[dim]Press 'l' from app detail for full logs[/]"
        )

    def _cmd_status(self) -> None:
        """Show system status."""
        # TODO: Fetch from API
        self._add_system_message(
            "[bold]System Status[/bold]\n"
            "─────────────────────\n"
            "CPU:    ████░░░░░░ 42%\n"
            "Memory: ██████░░░░ 63%\n"
            "Disk:   ████████░░ 81%\n"
            "Uptime: 14d 3h 22m\n"
            "\n"
            "Apps: [green]3 running[/], [dim]1 stopped[/], [red]1 failed[/]"
        )

    def _cmd_clear(self) -> None:
        """Clear chat history."""
        messages = self.query_one("#chat-messages", Static)
        self._chat_content = ""
        messages.update("")
        self._add_system_message("Chat cleared. Type ? for help.")

    def action_go_back(self) -> None:
        """Go back to dashboard."""
        self.app.switch_mode("dashboard")

    def on_key(self, event: Key) -> None:
        """Handle key events - ensure ESC works even with Input focused."""
        if event.key == "escape":
            event.prevent_default()
            self.action_go_back()
