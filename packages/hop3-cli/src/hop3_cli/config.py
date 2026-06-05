# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import contextlib
import dataclasses
import os
from pathlib import Path
from typing import Any, ClassVar, overload

import toml
from platformdirs import user_config_dir

# The prefix for all environment variables.
PREFIX = "HOP3_"

APP_NAME = "hop3-cli"
APP_AUTHOR = "Abilian SAS"

_marker = object()


@dataclasses.dataclass
class Context:
    """A named server context with connection details."""

    name: str
    api_url: str
    api_token: str = ""
    protected: bool = False
    ssh_user: str = "root"
    ssh_port: int = 22
    ssh_key: str = ""
    ssl_cert: str = ""
    verify_ssl: bool = True
    # ADR 036 D7/D8: default app used by this context when `--app` is not given
    # and no higher-priority source (env var, .hop3-app file, project config)
    # resolves one. Set/cleared via `hop3 use` or `hop3 context use --app`.
    default_app: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for TOML storage."""
        return {
            "api_url": self.api_url,
            "api_token": self.api_token,
            "protected": self.protected,
            "ssh_user": self.ssh_user,
            "ssh_port": self.ssh_port,
            "ssh_key": self.ssh_key,
            "ssl_cert": self.ssl_cert,
            "verify_ssl": self.verify_ssl,
            "default_app": self.default_app,
        }

    @staticmethod
    def from_dict(name: str, data: dict) -> Context:
        """Create Context from dictionary."""
        return Context(
            name=name,
            api_url=data.get("api_url", ""),
            api_token=data.get("api_token", ""),
            protected=data.get("protected", False),
            ssh_user=data.get("ssh_user", "root"),
            ssh_port=data.get("ssh_port", 22),
            ssh_key=data.get("ssh_key", ""),
            ssl_cert=data.get("ssl_cert", ""),
            verify_ssl=data.get("verify_ssl", True),
            default_app=data.get("default_app", ""),
        )


@dataclasses.dataclass
class Config:
    data: dict = dataclasses.field(default_factory=dict)
    config_file: Path | None = None
    _context_override: str | None = None  # For --context flag
    _server_override: str | None = None  # For --server flag
    _app_override: str | None = None  # For --app flag

    # These are the ultimate fallbacks if nothing is configured.
    defaults: ClassVar[dict] = {
        # No default api_url - unconfigured state should be detected
        # Developers should set HOP3_DEV_MODE=true for localhost defaults
        "api_version": "v1",
        "server_port": 8000,
        "ssh_user": "root",
        "api_token": "",  # Bearer token for authentication
        # api_key and api_secret should be managed in state, not config.
        # "api_key": None,
        # "api_secret": None,
    }

    def is_configured(self) -> bool:
        """Check if the CLI has been configured with a server URL.

        Returns True if api_url is set via:
        1. Environment variable (HOP3_API_URL)
        2. Current context
        3. Developer mode (HOP3_DEV_MODE=true enables localhost:8000)
        """
        if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
            return True

        if "HOP3_API_URL" in os.environ:
            return True

        context = self.get_current_context()
        return bool(context and context.api_url)

    def is_authenticated(self) -> bool:
        """Check if the CLI has authentication credentials.

        Returns True if api_token is set via:
        1. Environment variable (HOP3_API_TOKEN)
        2. Current context
        """
        if os.environ.get("HOP3_API_TOKEN"):
            return True

        context = self.get_current_context()
        return bool(context and context.api_token)

    def get_api_url(self) -> str | None:
        """Get the API URL if configured, None otherwise.

        Priority:
        1. HOP3_API_URL environment variable
        2. Current context's api_url
        3. Developer mode default (localhost:8000)
        """
        if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
            return self.get("api_url", "http://localhost:8000")

        if "HOP3_API_URL" in os.environ:
            return os.environ["HOP3_API_URL"]

        context = self.get_current_context()
        if context and context.api_url:
            return context.api_url

        return None

    def get_api_token(self) -> str | None:
        """Get the API token if configured, None otherwise.

        Priority:
        1. HOP3_API_TOKEN environment variable
        2. Current context's api_token
        """
        if "HOP3_API_TOKEN" in os.environ:
            return os.environ["HOP3_API_TOKEN"]

        context = self.get_current_context()
        if context and context.api_token:
            return context.api_token

        return None

    @staticmethod
    def from_dict(data: dict) -> Config:
        return Config(data=data)

    @staticmethod
    def from_toml_file(file: Path) -> Config:
        if not file.exists():
            # It's okay for the config file not to exist; we'll use defaults.
            return Config(data={}, config_file=file)

        with file.open() as f:
            try:
                data = toml.load(f)
                return Config(data=data, config_file=file)
            except toml.TomlDecodeError:
                # FIXME: abort instead of returning empty config?
                # Handle malformed config file gracefully.
                # You might want to log a warning here.
                return Config(data={}, config_file=file)

    def __getitem__(self, item):
        value = self.get(item)
        if value is _marker:
            raise KeyError(item)
        return value

    @overload
    def get(self, key: str) -> Any: ...

    @overload
    def get(self, key: str, default: str) -> str: ...

    @overload
    def get(self, key: str, default: bool) -> bool: ...

    @overload
    def get(self, key: str, default: int) -> int: ...

    @overload
    def get(self, key: str, default: None) -> Any: ...

    def get(self, key: str, default: Any = _marker) -> Any:
        """
        Retrieves a configuration value with a clear priority order.

        1. Environment Variable (e.g., HOP3_API_URL)
        2. Value from config file (e.g., api_url = "...")
        3. Provided default value for this method call.
        4. Class-level default value.
        """
        # 1. Check Environment Variable
        env_var_key = PREFIX + key.upper()
        if env_var_key in os.environ:
            return os.environ[env_var_key]

        # 2. Check value from config file data
        if key in self.data:
            return self.data[key]

        # 3. Check for a default value passed to this specific `get` call
        if default is not _marker:
            return default

        # 4. Check for a class-level default value
        if key in self.defaults:
            return self.defaults[key]

        # If not found anywhere, raise KeyError
        raise KeyError(key)

    def save(self, updates: dict | None = None) -> None:
        """Save the config to the TOML file.

        SECURITY: the config holds the JWT auth token. Two precautions:

        1. ``chmod 0600`` so other local users can't read it.
        2. Atomic write via tmpfile + ``os.replace`` so a crash mid-write
           can't leave the file truncated (and bricked, since auto-auth
           needs it readable).

        Args:
            updates: Optional dict merged into config before saving.
        """
        if not self.config_file:
            msg = "Cannot save: config_file path not set"
            raise ValueError(msg)

        if updates:
            self.data.update(updates)

        config_dir = self.config_file.parent
        config_dir.mkdir(parents=True, exist_ok=True)

        # Write to a sibling tmp file in the same directory (so the
        # final os.replace is atomic — same filesystem guaranteed).
        # NamedTemporaryFile + delete=False keeps the file readable on
        # the rename target path even if we crash before chmod runs.
        import tempfile  # noqa: PLC0415

        fd, tmp_path = tempfile.mkstemp(
            prefix=".config.toml.",
            suffix=".tmp",
            dir=config_dir,
        )
        try:
            with os.fdopen(fd, "w") as f:
                toml.dump(self.data, f)
                f.flush()
                os.fsync(f.fileno())
            # Tighten perms before swap-in so there's no window where
            # the final file is world-readable.
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self.config_file)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    # =========================================================================
    # Context Management
    # =========================================================================

    def set_context_override(self, context_name: str | None) -> None:
        """Set a context override (from --context flag)."""
        self._context_override = context_name

    def has_context_override(self) -> bool:
        """Check if a context override is set (from --context flag)."""
        return self._context_override is not None

    def set_server_override(self, server: str | None) -> None:
        """Set a server override (from the --server flag).

        The global flag parser consumes ``--server`` / ``-s`` before any
        subcommand runs (see ``commands/flags.py``). For app-scoped RPC
        commands the value feeds server resolution; for local config-
        authoring commands (``hop3 context init/add``) it would otherwise
        be discarded, so we stash it here for those handlers to read.
        """
        self._server_override = server

    def get_server_override(self) -> str | None:
        """Return the server passed via ``--server`` / ``-s``, if any."""
        return self._server_override

    def set_app_override(self, app: str | None) -> None:
        """Set an app override (from the --app flag). See set_server_override."""
        self._app_override = app

    def get_app_override(self) -> str | None:
        """Return the app passed via ``--app`` / ``-a``, if any."""
        return self._app_override

    def get_current_context_name(self) -> str | None:
        """Get the name of the current context.

        Priority (ADR 042 §Resolution chains, post-Step-7):
        1. Context override (--context flag)
        2. HOP3_CONTEXT environment variable
        3. current_context in global config file
        4. None if no contexts configured

        Per-project context selection now goes through
        ``.hop3-local.toml [current].context`` (read by
        ``hop3_cli.core.resolution.resolve_context``, not by this method).
        The legacy ``.hop3-context`` one-liner was retired in Step 7.
        """
        # 1. Check override from --context flag
        if self._context_override:
            return self._context_override

        # 2. Check environment variable
        env_context = os.environ.get("HOP3_CONTEXT")
        if env_context:
            return env_context

        # 3. Check global config file
        return self.data.get("current_context")

    def get_current_context(self) -> Context | None:
        """Get the current context object."""
        name = self.get_current_context_name()
        if not name:
            return None

        contexts = self.data.get("contexts", {})
        if name not in contexts:
            return None

        return Context.from_dict(name, contexts[name])

    def get_contexts(self) -> dict[str, Context]:
        """Get all configured contexts."""
        contexts_data = self.data.get("contexts", {})
        return {
            name: Context.from_dict(name, data) for name, data in contexts_data.items()
        }

    def add_context(
        self,
        name: str,
        api_url: str,
        api_token: str = "",
        protected: bool = False,
        **kwargs,
    ) -> None:
        """Add a new context.

        Args:
            name: Context name (e.g., "production", "staging")
            api_url: Server URL (e.g., "ssh://root@prod.example.com")
            api_token: Authentication token
            protected: If True, requires extra confirmation for destructive ops
            **kwargs: Additional context options (ssh_user, ssh_port, etc.)
        """
        if "contexts" not in self.data:
            self.data["contexts"] = {}

        context = Context(
            name=name,
            api_url=api_url,
            api_token=api_token,
            protected=protected,
            ssh_user=kwargs.get("ssh_user", "root"),
            ssh_port=kwargs.get("ssh_port", 22),
            ssh_key=kwargs.get("ssh_key", ""),
            ssl_cert=kwargs.get("ssl_cert", ""),
            verify_ssl=kwargs.get("verify_ssl", True),
        )
        self.data["contexts"][name] = context.to_dict()

        # If this is the first context, make it current
        if "current_context" not in self.data:
            self.data["current_context"] = name

        self.save()

    def remove_context(self, name: str) -> None:
        """Remove a context by name.

        Args:
            name: Context name to remove

        Raises:
            KeyError: If context does not exist
        """
        contexts = self.data.get("contexts", {})
        if name not in contexts:
            raise KeyError(name)

        del contexts[name]

        # If we removed the current context, clear it
        if self.data.get("current_context") == name:
            # Switch to another context if available
            if contexts:
                self.data["current_context"] = next(iter(contexts))
            else:
                self.data.pop("current_context", None)

        self.save()

    def use_context(self, name: str) -> bool:
        """Check if a context exists (for validation).

        Note: this no longer persists the context. Use ``set_global_context()``
        for global persistence; per-project context selection goes through
        ``hop3_cli.core.local_overlay.write_overlay`` (ADR 042) to write
        ``.hop3-local.toml``.

        Args:
            name: Context name to check

        Returns:
            True if context exists, False if not found
        """
        contexts = self.data.get("contexts", {})
        return name in contexts

    def set_global_context(self, name: str) -> None:
        """Set the global default context (persists to config file).

        This affects ALL terminals/shells. Use with caution.
        Prefer environment variable or local context file for safety.

        Args:
            name: Context name to set as global default

        Raises:
            KeyError: If context does not exist
        """
        contexts = self.data.get("contexts", {})
        if name not in contexts:
            raise KeyError(name)

        self.data["current_context"] = name
        self.save()

    def is_protected_context(self) -> bool:
        """Check if the current context is marked as protected."""
        context = self.get_current_context()
        return context.protected if context else False

    def has_contexts(self) -> bool:
        """Check if any contexts are configured."""
        return bool(self.data.get("contexts"))

    def update_context_token(self, token: str, context_name: str | None = None) -> None:
        """Update the API token for a context.

        Args:
            token: The new API token
            context_name: Context to update (default: current context)

        Raises:
            KeyError: If context does not exist.
        """
        name = context_name or self.get_current_context_name()

        if not name or name not in self.data.get("contexts", {}):
            raise KeyError(name or "(no current context)")

        self.data["contexts"][name]["api_token"] = token
        self.save()

    def set_default_app(self, app: str | None, context_name: str | None = None) -> str:
        """Set (or clear) the default app for a context (ADR 036 D7/D8).

        Args:
            app: The app name to set, or None/empty to clear.
            context_name: Context to update (default: current context).

        Returns:
            The name of the context that was updated.

        Raises:
            KeyError: If no context is set and none is provided.
        """
        name = context_name or self.get_current_context_name()
        if not name:
            msg = "No active context. Set one first with `hop3 context use <name>`."
            raise KeyError(msg)
        if name not in self.data.get("contexts", {}):
            msg = f"Unknown context: {name}"
            raise KeyError(msg)

        self.data["contexts"][name]["default_app"] = app or ""
        self.save()
        return name

    def get_default_app(self, context_name: str | None = None) -> str:
        """Return the default app for a context (ADR 036 D7/D8), or empty string."""
        name = context_name or self.get_current_context_name()
        if not name or name not in self.data.get("contexts", {}):
            return ""
        return self.data["contexts"][name].get("default_app", "") or ""

    def update_context_credentials(
        self,
        api_url: str | None = None,
        api_token: str | None = None,
        context_name: str | None = None,
        **kwargs,
    ) -> None:
        """Update credentials for a context.

        Args:
            api_url: Server URL (optional)
            api_token: API token (optional)
            context_name: Context to update (default: current context)
            **kwargs: Additional context options (verify_ssl, etc.)

        Raises:
            KeyError: If context does not exist.
        """
        name = context_name or self.get_current_context_name()

        if not name or name not in self.data.get("contexts", {}):
            raise KeyError(name or "(no current context)")

        ctx = self.data["contexts"][name]
        if api_url is not None:
            ctx["api_url"] = api_url
        if api_token is not None:
            ctx["api_token"] = api_token
        for key, value in kwargs.items():
            ctx[key] = value
        self.save()


def get_config(config_file: Path | str | None = None) -> Config:
    """
    Loads configuration from the standard user location or a specified file.
    """
    if config_file is None:
        # Use platform-specific user config directory
        config_dir = user_config_dir(APP_NAME, APP_AUTHOR)
        config_path = Path(config_dir) / "config.toml"
    else:
        config_path = Path(config_file)

    # Create directory if it doesn't exist to be user-friendly on first run
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = Config.from_toml_file(config_path)
    return config
