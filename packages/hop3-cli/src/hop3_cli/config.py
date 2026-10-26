# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import contextlib
import dataclasses
import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, overload

import toml

from hop3_cli.core import credential_store
from hop3_cli.core.paths import config_dir
from hop3_cli.core.ssh_target import is_ssh_address, ssh_target_from_address
from hop3_cli.exceptions import ConfigError, TargetError

if TYPE_CHECKING:
    from hop3_cli.core.target import Target

# The prefix for all environment variables.
PREFIX = "HOP3_"

_marker = object()


#: The context a login writes when the operator names none. Every target is a
#: named context (ADR 042 / tasks/cli-auth-target-model.md): an *unnamed*
#: default target resolved below every context, so it was silently ignored by
#: anyone who had one. Reserved for the global scope — a project may not use it.
DEFAULT_CONTEXT_NAME = "default"

#: The context the environment defines. `HOP3_API_URL` (and `HOP3_DEV_MODE`'s
#: localhost) name a target the same way a context does, and `get_api_url`
#: consults them ahead of any stored one. Giving that target a name puts it in
#: the model the operator already reads: `hop3 context` lists it, and the
#: warning before a destroy names it instead of needing a special case for it.
ENV_CONTEXT_NAME = "env"


@dataclasses.dataclass
class Config:
    data: dict = dataclasses.field(default_factory=dict)
    config_file: Path | None = None
    _context_override: str | None = None  # For --context flag
    _app_override: str | None = None  # For --app flag
    # The server this invocation connects to: the resolved target's, or the
    # address a login just signed in to. The token is looked up by it.
    _active_server: str | None = None
    _active_bootstrap: str | None = None
    # ADR 042: where this invocation goes, and why — or why it can go nowhere.
    # Set once by main.py before any command dispatches; the refusal is raised
    # only when a command asks for a server.
    _target: Target | None = None
    _target_error: TargetError | None = None
    # -y / --yes, for the local commands that ask before writing.
    _assume_yes: bool = False

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
        """Whether this invocation has a server to talk to (ADR 042)."""
        try:
            return bool(self.get_api_url())
        except TargetError:
            return False

    def is_authenticated(self) -> bool:
        """
        Check if the CLI has authentication credentials.

        True if ``HOP3_API_TOKEN`` is set, or the credential store holds a
        token for the server this invocation connects to.
        """
        if os.environ.get("HOP3_API_TOKEN"):
            return True
        server = self._resolve_token_server()
        return bool(server and credential_store.get_token(server))

    def set_target(self, target: Target) -> None:
        """Record where this invocation goes (ADR 042); main.py calls it once."""
        self._target = target
        self._target_error = None
        self.set_active_server(target.server)
        self.set_active_bootstrap(target.bootstrap)

    def set_target_error(self, error: TargetError) -> None:
        """Record why this invocation has no server, to raise when one is needed."""
        self._target = None
        self._target_error = error

    def get_target(self) -> Target | None:
        """The resolved target, or None when there is none (or none was wired)."""
        return self._target

    def require_target(self) -> Target:
        """The resolved target, or the refusal that explains why there is none."""
        if self._target is not None:
            return self._target
        if self._target_error is not None:
            raise self._target_error
        msg = "no context selected: hop3 context use <name>"
        raise TargetError(msg)

    def set_assume_yes(self, value: bool) -> None:
        """Record -y / --yes for local commands that confirm before writing."""
        self._assume_yes = value

    def assume_yes(self) -> bool:
        """Whether -y / --yes was given."""
        return self._assume_yes

    def set_active_bootstrap(self, address: str | None) -> None:
        """
        Record this invocation's ``ssh://`` bootstrap route (ADR 042).

        Wired alongside ``set_active_server`` from the same resolution, so the
        server a command talks to and the route it renews through always come
        from one context.
        """
        self._active_bootstrap = address or None

    def get_bootstrap_target(self) -> str | None:
        """
        The ``user@host`` this connection mints tokens through, if any.

        Renewal used to be gated on the *connection* itself being ``ssh://``,
        which tied unattended renewal to routing every command through a root
        shell. They are different roles: a context can speak HTTPS all day and
        still know an SSH route home for the moment its token expires.
        """
        address = self._active_bootstrap
        if not address:
            api_url = self.get_api_url()
            if is_ssh_address(api_url):
                address = api_url
        if not address:
            return None
        return ssh_target_from_address(address, self.get("ssh_user", "root"))

    def set_active_server(self, address: str | None) -> None:
        """
        Set the server this invocation connects to. Pass ``None`` to clear.

        ``get_api_url`` returns it, and ``get_api_token`` looks the token up
        by it in the credential store.
        """
        self._active_server = address or None

    def get_api_url(self) -> str | None:
        """
        The server this invocation connects to.

        The resolved target's server (``set_target``), or the one a login
        just signed in to. When main.py found no target, the refusal it
        recorded is raised here, the first moment a server is needed.

        A Config that was never wired (the TUI, tests) falls back to the
        server of ``get_current_context_name``.

        Raises:
            TargetError: when main.py recorded why there is no target.
        """
        if self._active_server:
            return self._active_server
        if self._target_error is not None:
            raise self._target_error
        name = self.get_current_context_name()
        return self.get_context_server(name) if name else None

    def get_api_token(self) -> str | None:
        """
        Get the API token if configured, None otherwise.

        Priority:
        1. HOP3_API_TOKEN environment variable (only when non-empty — see below)
        2. The per-server credential store, keyed by the connection's server

        An *empty* HOP3_API_TOKEN is ignored (treated as unset). The presence
        test used to disagree with ``is_authenticated``'s truthy test, so an
        empty value passed the local auth gate yet sent no Authorization header
        — a 401 with nothing explaining why a good stored token was ignored
        (audit 2026-06 C4).
        """
        if env_token := os.environ.get("HOP3_API_TOKEN"):
            return env_token
        server = self._resolve_token_server()
        return credential_store.get_token(server) if server else None

    def _resolve_token_server(self) -> str | None:
        """
        The credential-store key for the current connection's bearer token.

        All three token paths — the readers (``get_api_token``,
        ``is_authenticated``) and the writer (``update_context_token``) — MUST
        resolve the SAME key, keyed by the address we actually connect to
        (``get_api_url``). Otherwise a token written under one key is invisible
        to the readers: a successful login that still 401s, or prod's token
        keyed by an ``HOP3_API_URL`` host it was never minted for (audit 2026-06
        C1/C3). Keying by ``get_api_url`` makes URL and token resolve together by
        construction, so they can never point at different servers.
        """
        return self.get_api_url()

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
            except toml.TomlDecodeError as exc:
                # Fail loud: a malformed config must not masquerade as an empty
                # one (which reads as "logged out" / no server and hides the real
                # problem). Abort with the file and parse error so the user can
                # fix it.
                msg = f"Malformed config file {file}: {exc}"
                raise ConfigError(msg) from exc

    def __getitem__(self, item: str) -> object:
        value = self.get(item)
        if value is _marker:
            raise KeyError(item)
        return value

    @overload
    def get(self, key: str) -> object: ...

    @overload
    def get(self, key: str, default: str) -> str: ...

    @overload
    def get(self, key: str, default: bool) -> bool: ...

    @overload
    def get(self, key: str, default: int) -> int: ...

    @overload
    def get(self, key: str, default: None) -> object: ...

    def get(self, key: str, default: object = _marker) -> object:
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
        """
        Save the config to the TOML file.

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
        import tempfile  # ruff:ignore[import-outside-top-level]

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

    def env_context_server(self) -> str | None:
        """
        The target the environment names, if it names one.

        ``HOP3_DEV_MODE``'s localhost, then ``HOP3_API_URL`` — the two values
        ``get_api_url`` consults before any stored context. Exposed so the rest
        of the CLI can treat them as a context (``ENV_CONTEXT_NAME``) rather
        than as a separate system each caller has to remember.
        """
        if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
            return self.get("api_url", "http://localhost:8000")
        return os.environ.get("HOP3_API_URL") or None

    def get_current_context_name(self) -> str | None:
        """
        The context this invocation uses: the resolved target's (ADR 042).

        A Config that was never wired (the TUI, tests) answers with the same
        chain outside a project: ``--context``, ``HOP3_CONTEXT``, ``env``, the
        global current context.
        """
        if self._target is not None:
            return self._target.context
        if self._target_error is not None:
            return None
        if self._context_override:
            return self._context_override
        if env_context := os.environ.get("HOP3_CONTEXT"):
            return env_context
        if self.env_context_server():
            return ENV_CONTEXT_NAME
        return self.get_default_context()

    # ---- contexts (ADR 042: global, personal, secret-free) ------------------
    # A context is a server you can reach. It lives in config.toml as
    # ``[contexts.<name>]`` with a ``server`` and an optional ``bootstrap``;
    # the token stays in the credential store, so config.toml is secret-free.

    def get_context_server(self, name: str) -> str | None:
        """Server address for a global context, or None if it isn't defined."""
        if name == ENV_CONTEXT_NAME:
            return self.env_context_server()
        contexts = self.data.get("contexts")
        if isinstance(contexts, dict):
            block = contexts.get(name)
            if isinstance(block, dict) and isinstance(block.get("server"), str):
                return block["server"] or None
        return None

    def set_context_server(
        self, name: str, server: str, *, bootstrap: str | None = None
    ) -> None:
        """
        Define (or update) a global context's addresses. Persists.

        ``server`` is what every command connects to. ``bootstrap`` is the
        ``ssh://`` target used only to mint tokens — see ``get_context_bootstrap``.
        Passing ``bootstrap=None`` leaves any recorded one untouched, so a
        password or token login does not erase the SSH route a previous
        ``hop3 login <host>`` established.
        """
        contexts = self.data.get("contexts")
        if not isinstance(contexts, dict):
            contexts = {}
            self.data["contexts"] = contexts
        block = contexts.get(name)
        if not isinstance(block, dict):
            block = {}
            contexts[name] = block
        block["server"] = server
        if bootstrap:
            block["bootstrap"] = bootstrap
        self.save()

    def get_context_bootstrap(self, name: str) -> str | None:
        """
        The ``ssh://`` target that mints tokens for a context, if it has one.

        Separate from ``server`` because the two roles are different: everyday
        traffic goes to ``server`` (HTTPS for a server with an admin domain),
        while minting a token needs SSH access to the machine. Recording only
        the SSH target — as every login used to — made routine, read-only work
        run through a root shell.

        A context whose ``server`` is itself an ``ssh://`` address bootstraps
        through that, so the two coincide there and no separate key is written.
        """
        contexts = self.data.get("contexts")
        if not isinstance(contexts, dict):
            return None
        block = contexts.get(name)
        if not isinstance(block, dict):
            return None
        recorded = block.get("bootstrap")
        if isinstance(recorded, str) and recorded:
            return recorded
        server = block.get("server")
        return server if is_ssh_address(server) else None

    def remove_global_context(self, name: str) -> bool:
        """Drop a context. Returns True if it existed. Persists."""
        contexts = self.data.get("contexts")
        if isinstance(contexts, dict) and name in contexts:
            del contexts[name]
            if self.get_default_context() == name:
                self.set_default_context(None)  # also saves
            else:
                self.save()
            return True
        return False

    def mark_context_protected(self, name: str) -> None:
        """
        Remember that context ``name`` names a protected server. Persists.

        Learned from the server's refusal, and used only to warn ahead of
        time (``hop3 context use``): the server enforces the rule itself.
        """
        contexts = self.data.get("contexts")
        block = contexts.get(name) if isinstance(contexts, dict) else None
        if isinstance(block, dict) and not block.get("protected"):
            block["protected"] = True
            self.save()

    def is_context_protected(self, name: str) -> bool:
        """Whether a server refused a change through ``name`` as protected."""
        contexts = self.data.get("contexts")
        block = contexts.get(name) if isinstance(contexts, dict) else None
        return isinstance(block, dict) and block.get("protected") is True

    def rename_context(self, old: str, new: str) -> None:
        """Rename a context, and the global current context with it. Persists."""
        contexts = self.data.get("contexts")
        if not isinstance(contexts, dict) or old not in contexts:
            msg = f"context {old!r} is not defined"
            raise ConfigError(msg)
        contexts[new] = contexts.pop(old)
        if self.get_default_context() == old:
            self.set_default_context(new)  # also saves
        else:
            self.save()

    def list_global_contexts(self) -> dict[str, str]:
        """
        Map of ``name -> server`` for every global context with an address.

        Includes the environment's own target under ``ENV_CONTEXT_NAME`` when
        one is set. It is not in config.toml and outlives no shell, but it IS
        where commands are going — leaving it out of the list is how an
        exported variable stays invisible while overriding everything.
        """
        contexts = self.data.get("contexts")
        out: dict[str, str] = {}
        if isinstance(contexts, dict):
            for name, block in contexts.items():
                if isinstance(block, dict) and isinstance(block.get("server"), str):
                    out[name] = block["server"]
        if env_server := self.env_context_server():
            out[ENV_CONTEXT_NAME] = env_server
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

    def update_context_token(self, token: str) -> None:
        """
        Persist (or clear) the bearer token for the active/default server.

        ADR 042 r2: tokens live in the per-server credential store, keyed by the
        resolved server address — the active context's server when one is set
        (RPC commands), otherwise the configured default server (login/logout and
        other project-less commands). config.toml never holds a token. Pass an
        empty string to remove the token (logout).
        """
        server = self._resolve_token_server()
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
