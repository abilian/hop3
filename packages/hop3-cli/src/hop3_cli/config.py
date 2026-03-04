# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import ClassVar

import toml
from platformdirs import user_config_dir

# The prefix for all environment variables.
PREFIX = "HOP3_"

APP_NAME = "hop3-cli"
APP_AUTHOR = "Abilian SAS"

# Local context file name (per-project context)
LOCAL_CONTEXT_FILE = ".hop3-context"

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
        )


@dataclasses.dataclass
class Config:
    data: dict = dataclasses.field(default_factory=dict)
    config_file: Path | None = None
    _context_override: str | None = None  # For --context flag

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
        3. Legacy config file (api_url at top level)
        4. Developer mode (HOP3_DEV_MODE=true enables localhost:8000)

        Returns False if no server has been configured.
        """
        # Check for developer mode
        if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
            return True

        # Check environment variable
        if "HOP3_API_URL" in os.environ:
            return True

        # Check current context
        context = self.get_current_context()
        if context and context.api_url:
            return True

        # Check legacy config file (for backwards compatibility)
        return "api_url" in self.data

    def is_authenticated(self) -> bool:
        """Check if the CLI has authentication credentials.

        Returns True if api_token is set via:
        1. Environment variable (HOP3_API_TOKEN)
        2. Current context
        3. Legacy config file

        Returns False if no authentication token is available.
        """
        # Check environment variable
        if os.environ.get("HOP3_API_TOKEN"):
            return True

        # Check current context
        context = self.get_current_context()
        if context and context.api_token:
            return True

        # Check legacy config file
        token = self.data.get("api_token", "")
        return bool(token)

    def get_api_url(self) -> str | None:
        """Get the API URL if configured, None otherwise.

        Priority:
        1. HOP3_API_URL environment variable
        2. Current context's api_url
        3. Legacy api_url in config file
        4. Developer mode default (localhost:8000)
        """
        # Check for developer mode first
        if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
            # In dev mode, default to localhost but allow override
            return self.get("api_url", "http://localhost:8000")

        # Check environment variable
        if "HOP3_API_URL" in os.environ:
            return os.environ["HOP3_API_URL"]

        # Check current context
        context = self.get_current_context()
        if context and context.api_url:
            return context.api_url

        # Check legacy config file
        if "api_url" in self.data:
            return self.data["api_url"]

        return None

    def get_api_token(self) -> str | None:
        """Get the API token if configured, None otherwise.

        Priority:
        1. HOP3_API_TOKEN environment variable
        2. Current context's api_token
        3. Legacy api_token in config file
        """
        # Check environment variable
        if "HOP3_API_TOKEN" in os.environ:
            return os.environ["HOP3_API_TOKEN"]

        # Check current context
        context = self.get_current_context()
        if context and context.api_token:
            return context.api_token

        # Check legacy config file
        if "api_token" in self.data:
            return self.data["api_token"]

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

    def get(self, key, default=_marker):
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

        Args:
            updates: Optional dictionary of updates to merge into config before saving
        """
        if not self.config_file:
            msg = "Cannot save: config_file path not set"
            raise ValueError(msg)

        # Merge updates into data
        if updates:
            self.data.update(updates)

        # Ensure parent directory exists
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with self.config_file.open("w") as f:
            toml.dump(self.data, f)

    # =========================================================================
    # Context Management
    # =========================================================================

    def set_context_override(self, context_name: str | None) -> None:
        """Set a context override (from --context flag)."""
        self._context_override = context_name

    def has_context_override(self) -> bool:
        """Check if a context override is set (from --context flag)."""
        return self._context_override is not None

    def get_current_context_name(self) -> str | None:
        """Get the name of the current context.

        Priority:
        1. Context override (--context flag)
        2. HOP3_CONTEXT environment variable
        3. Local .hop3-context file (per-project)
        4. current_context in global config file
        5. None if no contexts configured
        """
        # 1. Check override from --context flag
        if self._context_override:
            return self._context_override

        # 2. Check environment variable
        env_context = os.environ.get("HOP3_CONTEXT")
        if env_context:
            return env_context

        # 3. Check local .hop3-context file
        local_context = self._read_local_context()
        if local_context:
            return local_context

        # 4. Check global config file
        return self.data.get("current_context")

    def _read_local_context(self) -> str | None:
        """Read context from local .hop3-context file if it exists."""
        local_file = Path.cwd() / LOCAL_CONTEXT_FILE
        if local_file.exists():
            try:
                content = local_file.read_text().strip()
                if content:
                    return content
            except OSError:
                pass
        return None

    @staticmethod
    def write_local_context(name: str) -> Path:
        """Write context to local .hop3-context file.

        Args:
            name: Context name to write

        Returns:
            Path to the created file
        """
        local_file = Path.cwd() / LOCAL_CONTEXT_FILE
        local_file.write_text(name + "\n")
        return local_file

    @staticmethod
    def get_local_context_path() -> Path:
        """Get the path to the local context file."""
        return Path.cwd() / LOCAL_CONTEXT_FILE

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

    def remove_context(self, name: str) -> bool:
        """Remove a context by name.

        Args:
            name: Context name to remove

        Returns:
            True if removed, False if not found
        """
        contexts = self.data.get("contexts", {})
        if name not in contexts:
            return False

        del contexts[name]

        # If we removed the current context, clear it
        if self.data.get("current_context") == name:
            # Switch to another context if available
            if contexts:
                self.data["current_context"] = next(iter(contexts))
            else:
                self.data.pop("current_context", None)

        self.save()
        return True

    def use_context(self, name: str) -> bool:
        """Check if a context exists (for validation).

        Note: This no longer persists the context. Use set_global_context()
        for global persistence or write_local_context() for local persistence.

        Args:
            name: Context name to check

        Returns:
            True if context exists, False if not found
        """
        contexts = self.data.get("contexts", {})
        return name in contexts

    def set_global_context(self, name: str) -> bool:
        """Set the global default context (persists to config file).

        This affects ALL terminals/shells. Use with caution.
        Prefer environment variable or local context file for safety.

        Args:
            name: Context name to set as global default

        Returns:
            True if set, False if context not found
        """
        contexts = self.data.get("contexts", {})
        if name not in contexts:
            return False

        self.data["current_context"] = name
        self.save()
        return True

    def is_protected_context(self) -> bool:
        """Check if the current context is marked as protected."""
        context = self.get_current_context()
        return context.protected if context else False

    def has_contexts(self) -> bool:
        """Check if any contexts are configured."""
        return bool(self.data.get("contexts"))

    def update_context_token(self, token: str, context_name: str | None = None) -> bool:
        """Update the API token for a context.

        If context_name is None, updates the current context.
        If no contexts exist, falls back to legacy top-level api_token.

        Args:
            token: The new API token
            context_name: Context to update (default: current context)

        Returns:
            True if token was saved to a context, False if saved to legacy format
        """
        name = context_name or self.get_current_context_name()

        if name and name in self.data.get("contexts", {}):
            # Save to context
            self.data["contexts"][name]["api_token"] = token
            self.save()
            return True

        # Fallback to legacy format
        self.data["api_token"] = token
        self.save()
        return False

    def update_context_credentials(
        self,
        api_url: str | None = None,
        api_token: str | None = None,
        context_name: str | None = None,
        **kwargs,
    ) -> bool:
        """Update credentials for a context.

        If context_name is None, updates the current context.
        If no contexts exist, falls back to legacy top-level config.

        Args:
            api_url: Server URL (optional)
            api_token: API token (optional)
            context_name: Context to update (default: current context)
            **kwargs: Additional context options (verify_ssl, etc.)

        Returns:
            True if saved to a context, False if saved to legacy format
        """
        name = context_name or self.get_current_context_name()

        if name and name in self.data.get("contexts", {}):
            # Save to context
            ctx = self.data["contexts"][name]
            if api_url is not None:
                ctx["api_url"] = api_url
            if api_token is not None:
                ctx["api_token"] = api_token
            for key, value in kwargs.items():
                ctx[key] = value
            self.save()
            return True

        # Fallback to legacy format
        updates = {}
        if api_url is not None:
            updates["api_url"] = api_url
        if api_token is not None:
            updates["api_token"] = api_token
        updates.update(kwargs)
        self.save(updates)
        return False

    def migrate_legacy_config(self) -> bool:
        """Migrate legacy single-server config to context format.

        If api_url is set at the top level (old format), migrate it
        to a "default" context.

        Returns:
            True if migration was performed, False otherwise
        """
        # Skip if already using contexts
        if self.data.get("contexts"):
            return False

        # Skip if no legacy config
        if "api_url" not in self.data:
            return False

        # Migrate to default context
        self.add_context(
            name="default",
            api_url=self.data.pop("api_url"),
            api_token=self.data.pop("api_token", ""),
            ssh_user=self.data.pop("ssh_user", "root"),
            ssh_port=self.data.pop("ssh_port", 22),
            ssh_key=self.data.pop("ssh_key", ""),
            ssl_cert=self.data.pop("ssl_cert", ""),
            verify_ssl=self.data.pop("verify_ssl", True),
        )
        return True


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
