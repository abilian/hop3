# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import contextlib
import dataclasses
import os
from pathlib import Path
from typing import Any, ClassVar, overload

import toml

from hop3_cli.core.paths import config_dir

# The prefix for all environment variables.
PREFIX = "HOP3_"

_marker = object()


@dataclasses.dataclass
class Context:
    """A legacy config.toml connection record (read-only fallback).

    ADR 042 r2 retired config.toml ``[contexts.*]`` as the connection source:
    deploy environments now live in the app's committed ``hop3.toml`` and bearer
    tokens live in the per-server credential store. This class survives only as a
    one-release *read* fallback so an un-migrated config.toml still resolves a
    connection until the startup migration drains it. Nothing writes it anymore.
    """

    name: str
    api_url: str
    api_token: str = ""

    @staticmethod
    def from_dict(name: str, data: dict) -> Context:
        """Create Context from dictionary (prefers ``url``/``token``)."""
        return Context(
            name=name,
            api_url=data.get("url") or data.get("api_url", ""),
            api_token=data.get("token") or data.get("api_token", ""),
        )


@dataclasses.dataclass
class Config:
    data: dict = dataclasses.field(default_factory=dict)
    config_file: Path | None = None
    _context_override: str | None = None  # For --context flag
    _app_override: str | None = None  # For --app flag
    # ADR 042 r2: the resolved context's server ADDRESS (from hop3.toml
    # [contexts.<name>].server). When set, the connection (url + token) is
    # resolved from this address + the per-server token store, not the legacy
    # config.toml context. Set per-invocation by main.py after context resolution.
    _active_server: str | None = None

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

        if self._active_server:
            return True

        if self.get_default_server():
            return True

        context = self.get_current_context()
        return bool(context and context.api_url)

    def is_authenticated(self) -> bool:
        """Check if the CLI has authentication credentials.

        Returns True if api_token is set via:
        1. Environment variable (HOP3_API_TOKEN)
        2. The per-server credential store (active or default server)
        3. Legacy config.toml context (one-release read fallback)
        """
        if os.environ.get("HOP3_API_TOKEN"):
            return True

        from hop3_cli.core import credential_store  # noqa: PLC0415

        server = self._active_server or self.get_default_server()
        if server:
            return bool(credential_store.get_token(server))

        context = self.get_current_context()
        return bool(context and context.api_token)

    def set_active_server(self, address: str | None) -> None:
        """Set the resolved-context server address (ADR 042 r2).

        When set, ``get_api_url`` / ``get_api_token`` resolve the connection from
        this address plus the per-server token store, instead of the legacy
        config.toml context. Pass ``None`` to clear.
        """
        self._active_server = address or None

    def get_api_url(self) -> str | None:
        """Get the API URL if configured, None otherwise.

        Priority:
        1. HOP3_API_URL environment variable
        2. The resolved context's server (``_active_server``)
        3. The configured default server (project-less commands)
        4. Legacy config.toml context (one-release read fallback)
        5. Developer mode default (localhost:8000)
        """
        if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
            return self.get("api_url", "http://localhost:8000")

        if "HOP3_API_URL" in os.environ:
            return os.environ["HOP3_API_URL"]

        if self._active_server:
            return self._active_server

        if default := self.get_default_server():
            return default

        context = self.get_current_context()
        if context and context.api_url:
            return context.api_url

        return None

    def get_api_token(self) -> str | None:
        """Get the API token if configured, None otherwise.

        Priority:
        1. HOP3_API_TOKEN environment variable
        2. The per-server credential store, keyed by the active or default server
        3. Legacy config.toml context (one-release read fallback)
        """
        if "HOP3_API_TOKEN" in os.environ:
            return os.environ["HOP3_API_TOKEN"]

        from hop3_cli.core import credential_store  # noqa: PLC0415

        server = self._active_server or self.get_default_server()
        if server:
            return credential_store.get_token(server)

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

        config.toml is secret-free under ADR 042 r2 (bearer tokens live in the
        per-server credential store), but we still write defensively:

        1. ``chmod 0600`` so other local users can't read local preferences.
        2. Atomic write via tmpfile + ``os.replace`` so a crash mid-write
           can't leave the file truncated (and bricked).

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

    def get_context_override(self) -> str | None:
        """Return the context name passed via ``--context`` / ``-c``, if any."""
        return self._context_override

    def set_app_override(self, app: str | None) -> None:
        """Set an app override (from the --app flag)."""
        self._app_override = app

    def get_app_override(self) -> str | None:
        """Return the app passed via ``--app`` / ``-a``, if any."""
        return self._app_override

    def get_current_context_name(self) -> str | None:
        """Get the name of the current context.

        Priority (ADR 042 §Resolution chains, post-Step-7):
        1. Context override (--context flag)
        2. HOP3_CONTEXT environment variable
        3. ``[cli].current_context`` in the global config file
        4. None if no contexts configured

        Per-project context selection now goes through
        ``.hop3-local.toml [local].context`` (read by
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

        # 3. Check global config file ([cli].current_context, legacy fallback)
        return self._read_current_context_pointer()

    # ---- current-context pointer (ADR 042: [cli].current_context) ----------

    def _read_current_context_pointer(self) -> str | None:
        """The persisted current-context name.

        Canonical location is ``[cli].current_context``; the legacy top-level
        ``current_context`` is read as a one-release fallback (downgrade window).
        """
        cli = self.data.get("cli")
        if isinstance(cli, dict) and isinstance(cli.get("current_context"), str):
            return cli["current_context"]
        val = self.data.get("current_context")
        return val if isinstance(val, str) else None

    def get_default_server(self) -> str | None:
        """The default-server address for project-less commands (ADR 042 r2).

        Stored at ``[cli].default_server`` in config.toml. The legacy *unnamed*
        default target for project-less commands, used when no ``--context`` and no
        ``[cli].default_context`` resolve a server. Prefer a named default context.
        """
        cli = self.data.get("cli")
        if isinstance(cli, dict) and isinstance(cli.get("default_server"), str):
            return cli["default_server"] or None
        return None

    def set_default_server(self, address: str | None) -> None:
        """Set (or clear) the default-server address. Persists immediately."""
        cli = self.data.get("cli")
        if not isinstance(cli, dict):
            cli = {}
            self.data["cli"] = cli
        if address:
            cli["default_server"] = address
        else:
            cli.pop("default_server", None)
        self.save()

    # ---- global contexts (ADR 042: named, project-less, secret-free) --------
    # A *global* context names a server you can select project-lessly with
    # ``--context <name>`` (e.g. `hop3 apps --context prod`). It lives in
    # config.toml as ``[contexts.<name>].server`` — an address only; the token
    # stays in the credential store, so config.toml is still secret-free.

    def get_context_server(self, name: str) -> str | None:
        """Server address for a global context, or None if it isn't defined."""
        contexts = self.data.get("contexts")
        if isinstance(contexts, dict):
            block = contexts.get(name)
            if isinstance(block, dict) and isinstance(block.get("server"), str):
                return block["server"] or None
        return None

    def set_context_server(self, name: str, server: str) -> None:
        """Define (or update) a global context's server address. Persists."""
        contexts = self.data.get("contexts")
        if not isinstance(contexts, dict):
            contexts = {}
            self.data["contexts"] = contexts
        block = contexts.get(name)
        if not isinstance(block, dict):
            block = {}
            contexts[name] = block
        block["server"] = server
        self.save()

    def remove_global_context(self, name: str) -> bool:
        """Drop a global context. Returns True if it existed. Persists."""
        contexts = self.data.get("contexts")
        if isinstance(contexts, dict) and name in contexts:
            del contexts[name]
            if self.get_default_context() == name:
                self.set_default_context(None)  # also saves
            else:
                self.save()
            return True
        return False

    def list_global_contexts(self) -> dict[str, str]:
        """Map of ``name -> server`` for every global context with an address."""
        contexts = self.data.get("contexts")
        out: dict[str, str] = {}
        if isinstance(contexts, dict):
            for name, block in contexts.items():
                if isinstance(block, dict) and isinstance(block.get("server"), str):
                    out[name] = block["server"]
        return out

    def get_default_context(self) -> str | None:
        """The default context name for project-less commands (``[cli].default_context``)."""
        cli = self.data.get("cli")
        if isinstance(cli, dict) and isinstance(cli.get("default_context"), str):
            return cli["default_context"] or None
        return None

    def set_default_context(self, name: str | None) -> None:
        """Set (or clear) the default context name. Persists immediately."""
        cli = self.data.get("cli")
        if not isinstance(cli, dict):
            cli = {}
            self.data["cli"] = cli
        if name:
            cli["default_context"] = name
        else:
            cli.pop("default_context", None)
        self.save()

    def get_current_context(self) -> Context | None:
        """Get the current context object."""
        name = self.get_current_context_name()
        if not name:
            return None

        contexts = self.data.get("contexts", {})
        if name not in contexts:
            return None

        return Context.from_dict(name, contexts[name])

    def update_context_token(self, token: str) -> None:
        """Persist (or clear) the bearer token for the active/default server.

        ADR 042 r2: tokens live in the per-server credential store, keyed by the
        resolved server address — the active context's server when one is set
        (RPC commands), otherwise the configured default server (login/logout and
        other project-less commands). config.toml never holds a token. Pass an
        empty string to remove the token (logout).
        """
        from hop3_cli.core import credential_store  # noqa: PLC0415

        server = self._active_server or self.get_default_server() or self.get_api_url()
        if not server:
            return
        if token:
            credential_store.set_token(server, token)
        else:
            credential_store.remove_token(server)


def get_config(config_file: Path | str | None = None) -> Config:
    """
    Loads configuration from the standard user location or a specified file.
    """
    if config_file is None:
        # Platform config dir, honoring $HOP3_CONFIG_DIR (see core.paths).
        config_path = config_dir() / "config.toml"
    else:
        config_path = Path(config_file)

    # Create directory if it doesn't exist to be user-friendly on first run
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = Config.from_toml_file(config_path)
    return config
