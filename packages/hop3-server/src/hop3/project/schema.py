# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pydantic schema for hop3.toml validation.

This module defines Pydantic models that validate hop3.toml configuration files.
The schema enforces:
- Known sections only (unknown sections are rejected)
- Correct types for all fields
- Valid values where applicable

When validation fails, clear error messages are provided to help users
fix their configuration.
"""

from __future__ import annotations

import re
from typing import Any, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# Context names live in user-facing flags (`hop3 context use <name>`) and
# in the .hop3-local.toml [current].context field. Keep them shell-friendly:
# start with a letter, then letters / digits / dash / underscore.
_CONTEXT_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")

# Names reserved for current/future CLI keywords (per ADR 042 §Reserved
# context names). Rejected at schema time so they never appear in a
# deployed config. Comparison is case-insensitive: `Default` and `DEFAULT`
# collide with `default` in CLI usage and are reserved too.
_RESERVED_CONTEXT_NAMES: frozenset[str] = frozenset({
    "default",
    "current",
    "global",
    "all",
    "none",
})


class MetadataSection(BaseModel):
    """[metadata] section - Application identity and catalog info."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    version: str | None = None
    title: str | None = None
    description: str | None = None
    author: str | None = None
    license: str | None = None
    name: str | None = None
    homepage: str | None = None
    categories: list[str] | None = None
    tags: list[str] | None = None


class BuildSection(BaseModel):
    """[build] section - Build-time configuration."""

    model_config = ConfigDict(extra="forbid")

    builder: str | None = Field(
        default=None,
        description="Builder to use: 'local', 'docker', or 'auto' (default)",
    )
    toolchain: str | None = Field(
        default=None,
        description="Language toolchain: 'python', 'node', 'ruby', 'go', 'rust', etc.",
    )
    before_build: str | list[str] | None = Field(
        default=None,
        alias="before-build",
        description="Commands to run before build",
    )
    after_build: str | list[str] | None = Field(
        default=None,
        alias="after-build",
        description="Commands to run after build (post-build)",
    )
    build: str | list[str] | None = Field(
        default=None,
        description="Build commands",
    )
    test: str | list[str] | None = Field(
        default=None,
        description="Test/smoke test commands",
    )
    packages: list[str] | None = Field(
        default=None,
        description="System packages required for build",
    )
    node_version: str | None = Field(
        default=None,
        alias="node-version",
        description=(
            "Per-app Node.js version (installed via nodeenv into the "
            "app's virtualenv). Use when the app requires a Node "
            "newer/older than the host's system Node. Maps to "
            "NODE_VERSION env var internally."
        ),
    )
    pip_install: list[str] | None = Field(
        default=None,
        alias="pip-install",
        description="Python packages to install",
    )
    ignore: list[str] | None = Field(
        default=None,
        description=(
            "Gitignore-style patterns to exclude from the `hop3 deploy` upload, "
            "on top of Hop3's built-in defaults (ADR 046 §5). The canonical "
            "ignore mechanism — the `.hop3ignore` sidecar and the `ignore-file` "
            "pointer are removed."
        ),
    )

    @field_validator("builder")
    @classmethod
    def validate_builder(cls, v: str | None) -> str | None:
        if v is not None:
            valid_builders = {"auto", "local", "docker", "nix"}
            if v.lower() not in valid_builders:
                msg = f"Invalid builder '{v}'. Must be one of: {', '.join(valid_builders)}"
                raise ValueError(msg)
        return v


class RunSection(BaseModel):
    """[run] section - Runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    start: str | list[str] | None = Field(
        default=None,
        description="Start command for the web process",
    )
    before_run: str | list[str] | None = Field(
        default=None,
        alias="before-run",
        description="Commands to run before starting the app",
    )
    workers: dict[str, str] | None = Field(
        default=None,
        description="Named worker processes (worker, scheduler, cron, etc.)",
    )
    start_timeout: int | float | None = Field(
        default=None,
        alias="start-timeout",
        description="Maximum time to wait for app to start (seconds)",
    )
    packages: list[str] | None = Field(
        default=None,
        description="System packages required at runtime",
    )
    static: dict[str, str] | None = Field(
        default=None,
        description="Static file path mappings (URL path -> filesystem path)",
    )
    healthcheck: str | None = Field(
        default=None,
        description="Health check HTTP path",
    )
    healthcheck_timeout: int | None = Field(
        default=None,
        alias="healthcheck-timeout",
        description="Health check timeout in seconds",
    )


class PortConfig(BaseModel):
    """Port configuration for a single port (full format)."""

    model_config = ConfigDict(extra="forbid")

    container: int | None = Field(
        default=None,
        description="Internal container port",
    )
    public: bool = Field(
        default=True,
        description="Whether the port is publicly accessible",
    )
    https: bool = Field(
        default=True,
        description="Whether HTTPS is enabled",
    )


# Port can be either a simple int or a full PortConfig
PortValue = int | PortConfig


class DockerSection(BaseModel):
    """[docker] section - Docker-specific configuration."""

    model_config = ConfigDict(extra="forbid")

    port: int | None = Field(
        default=None,
        description="Container port for Docker deployments",
    )
    runtime: str | None = Field(
        default=None,
        description="Docker runtime: 'docker' (default) or 'docker-compose'",
    )
    build_args: dict[str, str] | None = Field(
        default=None,
        alias="build-args",
        description="Docker build arguments",
    )


class HealthcheckSection(BaseModel):
    """[healthcheck] section - Health monitoring configuration."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = Field(
        default=None,
        description="Health check HTTP path",
    )
    interval: int | None = Field(
        default=None,
        description="Check interval in seconds",
    )
    timeout: int | None = Field(
        default=None,
        description="Timeout in seconds",
    )
    retries: int | None = Field(
        default=None,
        description="Number of retries before marking unhealthy",
    )


class BackupSection(BaseModel):
    """[backup] section - Backup configuration."""

    model_config = ConfigDict(extra="forbid")

    paths: list[str] | None = Field(
        default=None,
        description="Directories to include in backups",
    )
    exclude: list[str] | None = Field(
        default=None,
        description="Patterns to exclude from backups",
    )


class DomainsSection(BaseModel):
    """[domains] section - First-class declaration of an app's hostnames.

    Translates at deploy time into the HOST_NAME env var, which the reverse-
    proxy plugins (nginx/caddy/traefik) read. Mirrors the [env] policy model:
    by default values are treated as defaults (keep-existing); set
    ``_policy = "override"`` to update HOST_NAME on every deploy.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    hosts: list[str] = Field(
        alias="list",
        description="Hostnames to bind to this app, in declaration order.",
    )
    policy: str | None = Field(
        default=None,
        alias="_policy",
        description="Merge policy: 'keep-existing' (default) or 'override'.",
    )

    @field_validator("hosts")
    @classmethod
    def validate_hosts(cls, v: list[str]) -> list[str]:
        # "_" is the nginx catch-all; meaningful only as the sole entry.
        if "_" in v and len(v) > 1:
            msg = (
                "The catch-all hostname '_' cannot be combined with other "
                "hostnames in [domains].list."
            )
            raise ValueError(msg)
        return v

    @field_validator("policy")
    @classmethod
    def validate_policy(cls, v: str | None) -> str | None:
        if v is not None and v not in {"keep-existing", "override"}:
            msg = (
                f"Invalid [domains]._policy {v!r}. "
                "Must be 'keep-existing' or 'override'."
            )
            raise ValueError(msg)
        return v


class ContextSection(BaseModel):
    """A single [contexts.<name>] block — one project deploy target.

    A "context" in the ADR-042 sense is a (server, app, domains, env)
    bundle: it answers "where does *this* project go when I run a command
    against context <name>?". Multiple contexts cover the dev / staging /
    prod story for the same codebase.

    Field semantics:
    - ``server`` (required) names a server defined in the user's global
      registry (``~/.config/hop3-cli/servers.toml``). The schema does
      **not** validate cross-file references — a server name unknown to
      the schema may still be valid at runtime.
    - ``app``, ``domains``, ``env`` are optional overrides. When absent,
      the resolver falls back to top-level ``[metadata].id`` / ``[domains]``
      / ``[env]`` respectively.

    Notable asymmetries with top-level sections (deliberate, see ADR 042):
    - ``domains`` is a bare ``list[str]`` here (no ``_policy`` field).
      A context's domains *replace* the top-level ``[domains].list``
      when the resolver builds the deploy target. Per-context policy
      and merge semantics are ADR 042 open question #3 / #5.
    - ``env`` is a flat ``dict[str, Any]`` — the same value type as the
      top-level ``[env]`` so TOML scalars (booleans, ints) are accepted
      without quoting — but ``_policy`` and ``[env.computed]`` sub-tables
      are *not* honored at the context layer. Per-context env merge
      semantics with top-level ``[env]`` are ADR 042 open question #3.
    """

    model_config = ConfigDict(extra="forbid")

    server: str = Field(
        description=(
            "Name of a server defined in the global server registry "
            "(~/.config/hop3-cli/servers.toml). Required."
        ),
    )
    app: str | None = Field(
        default=None,
        description=(
            "App name on the target server. When absent, inherits from [metadata].id."
        ),
    )
    domains: list[str] | None = Field(
        default=None,
        description=(
            "Hostnames for this context. When absent, inherits from the "
            "top-level [domains].list. When present, fully replaces the "
            "top-level list — no merge, no per-context _policy."
        ),
    )
    env: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Env-var overrides scoped to this context. Value type matches "
            "the top-level [env] section (any TOML scalar). Per-context "
            "_policy and [env.computed] sub-tables are not honored."
        ),
    )

    @field_validator("server")
    @classmethod
    def validate_server(cls, v: str) -> str:
        # Reject empty AND whitespace-padded; do not silently strip.
        # Returning a value different from what the user wrote would
        # produce confusing diagnostics later (`server = " dev "` on disk
        # vs `server == "dev"` in resolution traces).
        if not v or v != v.strip():
            msg = (
                "Context.server must be a non-empty server name without "
                "leading or trailing whitespace."
            )
            raise ValueError(msg)
        return v

    @field_validator("app")
    @classmethod
    def validate_app(cls, v: str | None) -> str | None:
        # Per ADR 042 §App resolution, a context's `app` is a load-bearing
        # source for app identity. An empty or whitespace-only string here
        # would silently override the [metadata].id fallback with "the app
        # named empty-string" — caught at schema time to avoid an opaque
        # deploy-time failure.
        if v is None:
            return v
        if not v or v != v.strip():
            msg = (
                "Context.app must be a non-empty app name without leading "
                "or trailing whitespace. To inherit from [metadata].id, "
                "omit the `app` field entirely."
            )
            raise ValueError(msg)
        return v

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, v: list[str] | None) -> list[str] | None:
        # Two checks, both local to ContextSection so the section is
        # self-validating (avoiding action-at-a-distance with the top-level
        # [domains] block):
        # 1) Reject empty/whitespace-only entries — parity with `server`
        #    and `app` validators above; a literal "" hostname is never
        #    what the user meant.
        # 2) Mirror DomainsSection.validate_hosts: "_" is the nginx catch-
        #    all; it is meaningful only as the sole entry.
        if v is None:
            return v
        for entry in v:
            if not entry or entry != entry.strip():
                msg = (
                    "Context.domains entries must be non-empty hostnames "
                    "without leading or trailing whitespace."
                )
                raise ValueError(msg)
        if "_" in v and len(v) > 1:
            msg = (
                "The catch-all hostname '_' cannot be combined with other "
                "hostnames in a context's domains list."
            )
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_domains_vs_env_hostname(self) -> ContextSection:
        # Same invariant as the top-level Hop3TomlSchema validator: declaring
        # both a context-level `domains` list and a context-level
        # `env.HOST_NAME` would let the resolver silently pick one. Catch at
        # schema time so the error names the bad context section explicitly.
        if (
            self.domains is not None
            and self.env is not None
            and "HOST_NAME" in self.env
        ):
            msg = (
                "HOST_NAME cannot be set in a context's [env] when the same "
                "context also declares `domains`. Keep one or the other."
            )
            raise ValueError(msg)
        return self


def _validate_context_name(name: str) -> str:
    """Reject context names that won't survive shell/CLI surfaces.

    Context names appear unquoted on the command line and as keys in
    .hop3-local.toml. Two checks, in order so the user sees the most
    specific error first:

    1. **Reserved names** (case-insensitive): ``default``, ``current``,
       ``global``, ``all``, ``none`` — reserved for current/future CLI
       keywords. Rejected with an actionable message naming the full
       reserved set.
    2. **Identifier shape**: must start with a letter, then letters /
       digits / dash / underscore. Covers ``dev``, ``staging``, ``prod``,
       ``pre-prod``, ``qual_2`` and similar.
    """
    if name.lower() in _RESERVED_CONTEXT_NAMES:
        reserved = ", ".join(sorted(_RESERVED_CONTEXT_NAMES))
        msg = (
            f"Context name {name!r} is reserved for CLI keywords. "
            f"Reserved names (case-insensitive): {reserved}. "
            "Pick a different name."
        )
        raise ValueError(msg)
    if not _CONTEXT_NAME_RE.match(name):
        msg = (
            f"Invalid context name {name!r}. Context names must start with "
            "a letter and contain only letters, digits, '-' or '_'."
        )
        raise ValueError(msg)
    return name


class AddonConfig(BaseModel):
    """Single addon/provider configuration."""

    model_config = ConfigDict(extra="allow")  # Allow addon-specific options

    # 'type' is the modern field name, 'name' is deprecated but still supported
    type: str | None = Field(
        default=None,
        description="Addon type: 'postgres', 'mysql', 'redis', etc.",
    )
    name: str | None = Field(
        default=None,
        description="Addon instance name (legacy: also used as type in older configs)",
    )


# Host ports owned by the platform — apps may never claim them. 80/443 are the
# reverse proxy; 22 is SSH. (HTTP apps use $PORT and are proxied, not [[ports]].)
RESERVED_PORTS = frozenset({22, 80, 443})


class PortDeclaration(BaseModel):
    """A single [[ports]] entry — one fixed network port the app binds directly.

    For non-HTTP services (SMTP, XMPP, RTMP, Matrix federation, …) there is no
    reverse proxy or virtual hosting: the app binds the host port itself, so
    exactly one app can own a given (number, protocol) on the host. Declaring
    it lets Hop3 register the claim, refuse a conflicting second app up front,
    and open/close the firewall for it. The HTTP port stays dynamic (``$PORT``,
    proxied by nginx) and must NOT be declared here.
    """

    model_config = ConfigDict(extra="forbid")

    number: int = Field(description="Port number (1-65535, excluding 22/80/443).")
    protocol: str = Field(
        default="tcp", description="Transport protocol: 'tcp' or 'udp'."
    )
    name: str | None = Field(
        default=None,
        description="Optional label for diagnostics (e.g. 'rtmp', 'federation').",
    )

    @field_validator("number")
    @classmethod
    def _check_number(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            msg = f"Port number must be between 1 and 65535, got {v}"
            raise ValueError(msg)
        if v in RESERVED_PORTS:
            msg = (
                f"port {v} is reserved by Hop3 (80/443 belong to the reverse "
                f"proxy, 22 to SSH). HTTP apps are served on a dynamic $PORT "
                f"behind the proxy — don't declare 80/443/22 in [[ports]]."
            )
            raise ValueError(msg)
        return v

    @field_validator("protocol")
    @classmethod
    def _check_protocol(cls, v: str) -> str:
        if v not in {"tcp", "udp"}:
            msg = f"Protocol must be 'tcp' or 'udp', got {v!r}"
            raise ValueError(msg)
        return v


class TestValidation(BaseModel):
    """A single [[test.validations]] entry — one HTTP check the test harness
    performs after the app is up.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: str = Field(
        default="http",
        description="Validation type. Currently only 'http' is supported.",
    )
    path: str = Field(default="/", description="URL path to probe.")
    status: int = Field(default=200, description="Expected HTTP status code.")
    status_in: list[int] | None = Field(
        default=None,
        alias="status-in",
        description=(
            "Accept any of these status codes. Useful for apps whose first-"
            "boot install wizard legitimately returns 202 before migrations "
            "complete (e.g., xwiki). When set, `status` is ignored."
        ),
    )
    contains: str | None = Field(
        default=None,
        description="If set, response body must contain this substring.",
    )


class TestSection(BaseModel):
    """[test] section — test-harness-specific fields.

    Everything the test harness needs that cannot be derived from the rest
    of hop3.toml. Fields like name / description / category / services /
    deployment type are derived (from metadata, build.builder, addons).

    Replaces the separate `test.toml` file — one source of truth per app.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    priority: str | None = Field(
        default=None,
        description="Test priority: 'P0' | 'P1' | 'P2'. Selects which profile runs it.",
    )
    tier: str | None = Field(
        default=None,
        description=(
            "Test-tier label, used in reports only (no longer drives any "
            "timeout). Values: 'fast' | 'medium' | 'slow' | 'very-slow'."
        ),
    )
    targets: list[str] | None = Field(
        default=None,
        description="Test targets this app supports: 'docker' | 'remote'.",
    )
    author: str | None = None
    covers: list[str] | None = Field(
        default=None,
        description="Free-form tags listing what the test exercises.",
    )
    validations: list[TestValidation] | None = Field(
        default=None,
        description="HTTP checks beyond the single [healthcheck] endpoint.",
    )
    expects_failure: bool = Field(
        default=False,
        alias="expects-failure",
        description=(
            "Negative test case: the deploy is expected to fail. The runner "
            "treats a failed deploy as PASS and an unexpected successful "
            "deploy as FAIL. Used for ADR 039 Python-toolchain rejection "
            "paths and similar intentional-failure fixtures."
        ),
    )

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in {"P0", "P1", "P2"}:
            msg = f"Invalid test priority '{v}'. Must be one of: P0, P1, P2"
            raise ValueError(msg)
        return v

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str | None) -> str | None:
        if v is not None and v not in {"fast", "medium", "slow", "very-slow"}:
            msg = (
                f"Invalid test tier '{v}'. Must be one of: "
                "fast, medium, slow, very-slow"
            )
            raise ValueError(msg)
        return v

    @field_validator("targets")
    @classmethod
    def validate_targets(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        valid = {"docker", "remote"}
        for target in v:
            if target not in valid:
                msg = f"Invalid test target '{target}'. Must be one of: {sorted(valid)}"
                raise ValueError(msg)
        return v


# Secret generators available to `[env]` `{ generate = ... }` (ADR 046).
# hex/base64/urlsafe/password honour an optional `length`; uuid ignores it.
GENERATE_KINDS: frozenset[str] = frozenset({
    "hex",
    "base64",
    "urlsafe",
    "password",
    "uuid",
})


class EnvGenerate(BaseModel):
    """An `[env]` value the platform generates once on first deploy (ADR 046).

    Replaces the per-app ``hop3 deploy --env KEY=$(...)`` workaround for apps
    that need a secret/key to exist before first boot (Phoenix SECRET_KEY_BASE,
    Laravel APP_KEY, Rails secret_key_base). The value is generated with a
    CSPRNG when the var is unset, persisted as a normal app env var, and never
    regenerated on redeploy (generated-once).
    """

    model_config = ConfigDict(extra="forbid")

    generate: str = Field(
        description="Generator: 'hex', 'base64', 'urlsafe', 'password', or 'uuid'.",
    )
    length: int | None = Field(
        default=None,
        description=(
            "Entropy size: bytes for hex/base64/urlsafe, characters for "
            "password. Ignored for uuid. Per-generator default when omitted."
        ),
    )
    prefix: str | None = Field(
        default=None,
        description="Literal string prepended to the value (e.g. 'base64:').",
    )
    display: bool = Field(
        default=False,
        description="Surface the value once in deploy output (bootstrap creds).",
    )

    @field_validator("generate")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in GENERATE_KINDS:
            msg = (
                f"Invalid [env] generator {v!r}. "
                f"Must be one of: {', '.join(sorted(GENERATE_KINDS))}."
            )
            raise ValueError(msg)
        return v

    @field_validator("length")
    @classmethod
    def _check_length(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            msg = f"[env] generate length must be >= 1, got {v}."
            raise ValueError(msg)
        return v


class EnvRef(BaseModel):
    """An `[env]` value resolved from a fact at deploy time (ADR 046 §1b).

    For what auto-injection and `[env.computed]` can't express:
    - ``{ from = "<addon>", key = "<KEY>" }`` copies one attribute from a
      declared addon's credentials (``key`` is one of the addon's injected
      var names, e.g. ``DATABASE_URL``).
    - ``{ key = "domain" }`` (no ``from``) reads an app fact (``domain`` /
      ``hostname`` / ``name``).
    - ``{ external_ip = true }`` is the host's public IP (not yet implemented).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str | None = Field(
        default=None,
        alias="from",
        description="Name of a declared addon to read from; omit for app facts.",
    )
    key: str | None = Field(
        default=None,
        description="Attribute to copy (addon var name, or an app fact).",
    )
    external_ip: bool = Field(
        default=False,
        description="Resolve to the host's detected public IP.",
    )

    @model_validator(mode="after")
    def _check_shape(self) -> EnvRef:
        if self.external_ip:
            if self.from_ or self.key:
                msg = "external_ip cannot be combined with 'from' or 'key'."
                raise ValueError(msg)
            return self
        if not self.key:
            msg = (
                "a reference needs 'key' (with optional 'from'), or external_ip = true."
            )
            raise ValueError(msg)
        return self


# Volume types for `[[volumes]]` (ADR 046 §2). Only "persist" is implemented;
# tmpfs/bind need privileged mounts and fail loud at deploy until then.
VOLUME_TYPES: frozenset[str] = frozenset({"persist", "tmpfs", "bind"})

_VOLUME_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class VolumeBackupSection(BaseModel):
    """`[volumes.backup]` — per-volume backup policy (ADR 046 §2/§4a).

    A strict table so a typo (e.g. ``inclide = false``) is rejected at deploy
    time rather than silently leaving the volume in the backup. ``include``
    (default true) is the only key acted on today.
    """

    model_config = ConfigDict(extra="forbid")

    include: bool = Field(
        default=True,
        description="Whether this volume's data is captured by `hop3 backup create`.",
    )


class VolumeSection(BaseModel):
    """A `[[volumes]]` entry — a path that survives the source-replacing redeploy.

    ``persist`` (the default, and the only implemented type) links ``target`` —
    a directory inside the app's source tree — to storage under the app's data
    root (`<app>/volumes/<name>/`), so writes outlive the redeploy that wipes
    `src/`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description="Logical volume name; storage lives at <app>/volumes/<name>.",
    )
    target: str = Field(
        description="Directory inside the app tree to back with the volume (relative).",
    )
    type: str = Field(
        default="persist", description="persist (default) | tmpfs | bind."
    )
    size: str | None = Field(
        default=None, description="Size cap for a tmpfs volume (e.g. '256M')."
    )
    mode: str | None = Field(
        default=None, description="Octal permissions for the volume directory."
    )
    backup: VolumeBackupSection | None = Field(
        default=None,
        description="Per-volume backup policy; omit to include the volume in backups.",
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not _VOLUME_NAME_RE.match(v):
            msg = (
                f"Invalid [[volumes]] name {v!r}. Use letters, digits, '-' or '_' "
                "(starting with a letter or digit)."
            )
            raise ValueError(msg)
        return v

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in VOLUME_TYPES:
            msg = (
                f"Invalid [[volumes]] type {v!r}. "
                f"Must be one of: {', '.join(sorted(VOLUME_TYPES))}."
            )
            raise ValueError(msg)
        return v

    @field_validator("target")
    @classmethod
    def _check_target(cls, v: str) -> str:
        if not v or v.startswith("/"):
            msg = (
                f"[[volumes]] target {v!r} must be a non-empty path relative to the "
                "app tree (not absolute)."
            )
            raise ValueError(msg)
        if ".." in v.split("/"):
            msg = (
                f"[[volumes]] target {v!r} must not contain '..' "
                "(no escaping the app tree)."
            )
            raise ValueError(msg)
        return v

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                int(v, 8)
            except ValueError:
                msg = f"[[volumes]] mode {v!r} must be an octal string, e.g. '0700'."
                raise ValueError(msg) from None
        return v

    @model_validator(mode="after")
    def _check_size_only_for_tmpfs(self) -> VolumeSection:
        # `size` only means anything for a (not-yet-implemented) tmpfs volume;
        # accepting it on a persist volume would silently do nothing.
        if self.size is not None and self.type != "tmpfs":
            msg = (
                f"[[volumes]] {self.name!r}: 'size' is only valid for tmpfs "
                "volumes (which are not implemented yet)."
            )
            raise ValueError(msg)
        return self


_MEMORY_RE = re.compile(r"^\d+[KMGkmg]?$")


class LimitsSection(BaseModel):
    """[limits] section — per-app resource caps (ADR 046 §3).

    A declared limit is a safety guarantee: if the platform can't enforce it the
    deploy aborts rather than running an app that only *looks* capped. Today
    enforcement is implemented for the Docker builder (compose mem_limit / cpus /
    pids_limit); native/Nix enforcement needs cgroups via hop3-rootd and isn't
    available yet, so [limits] on a non-Docker app fails loud at deploy.
    """

    model_config = ConfigDict(extra="forbid")

    memory: str | None = Field(
        default=None, description="Hard memory cap, e.g. '512M' or '1G'."
    )
    cpu: float | None = Field(
        default=None, description="CPU cores, fractional allowed (e.g. 1.5)."
    )
    processes: int | None = Field(
        default=None, description="Max processes/threads (pids cap)."
    )

    @field_validator("memory")
    @classmethod
    def _check_memory(cls, v: str | None) -> str | None:
        if v is not None and not _MEMORY_RE.match(v):
            msg = (
                f"[limits] memory {v!r} must be a number with an optional K/M/G "
                "suffix, e.g. '512M' or '1G'."
            )
            raise ValueError(msg)
        return v

    @field_validator("cpu")
    @classmethod
    def _check_cpu(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            msg = f"[limits] cpu must be greater than 0, got {v}."
            raise ValueError(msg)
        return v

    @field_validator("processes")
    @classmethod
    def _check_processes(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            msg = f"[limits] processes must be >= 1, got {v}."
            raise ValueError(msg)
        return v


class Hop3TomlSchema(BaseModel):
    """Complete hop3.toml schema with validation.

    This schema validates the entire hop3.toml file and rejects unknown
    top-level sections. Each section has its own validation rules.

    Example hop3.toml:
        [metadata]
        id = "myapp"

        [build]
        builder = "local"
        before-build = "npm install"

        [run]
        start = "gunicorn app:app -b 0.0.0.0:$PORT"
        before-run = ["python manage.py migrate"]

        [run.workers]
        worker = "celery -A app worker"

        [env]
        DEBUG = "false"
    """

    model_config = ConfigDict(
        extra="forbid",  # Reject unknown top-level sections
        populate_by_name=True,  # Allow both alias and field name
    )

    metadata: MetadataSection | None = None
    build: BuildSection | None = None
    run: RunSection | None = None
    env: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Environment variables. "
            "Set _policy = 'override' to update existing values on redeploy."
        ),
    )
    port: dict[str, PortValue] | None = None
    docker: DockerSection | None = None
    healthcheck: HealthcheckSection | None = None
    backup: BackupSection | None = None
    static: dict[str, str] | None = Field(
        default=None,
        description="Static file path mappings (URL path -> filesystem path)",
    )
    domains: DomainsSection | None = Field(
        default=None,
        description=(
            "App hostnames. Translates to HOST_NAME at deploy time. Mutually "
            "exclusive with setting HOST_NAME under [env]."
        ),
    )
    contexts: dict[str, ContextSection] | None = Field(
        default=None,
        description=(
            "Per-project deploy targets (ADR 042). Each [contexts.<name>] "
            "block bundles (server, app, domains, env) for one operational "
            "mode — typically dev / staging / prod. Pure data at this stage; "
            "resolution happens in the CLI."
        ),
    )
    addons: list[AddonConfig] | None = None
    ports: list[PortDeclaration] | None = Field(
        default=None,
        description=(
            "Fixed host ports the app binds directly (non-HTTP services: SMTP, "
            "XMPP, RTMP, Matrix federation, …). Each is claimed exclusively on "
            "the host; a second app declaring the same port is refused before "
            "deploy. The HTTP port stays dynamic ($PORT, proxied) — don't list "
            "it here."
        ),
    )
    volumes: list[VolumeSection] | None = Field(
        default=None,
        description=(
            "Declarative persistent volumes (ADR 046 §2). Each links a directory "
            "in the app tree to storage that survives the source-replacing "
            "redeploy."
        ),
    )
    limits: LimitsSection | None = Field(
        default=None,
        description=(
            "Per-app resource caps (ADR 046 §3): memory / cpu / processes. "
            "Enforced for Docker apps; declaring them on a non-Docker app fails "
            "loud until cgroup enforcement lands."
        ),
    )
    provider: list[AddonConfig] | None = Field(
        default=None,
        description="Deprecated: use [[addons]] instead",
    )
    test: TestSection | None = Field(
        default=None,
        description=(
            "Test-harness metadata. Replaces the separate test.toml file — "
            "see TestSection for fields."
        ),
    )
    nix: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Nix template configuration for auto-generating hop3.nix. "
            "Requires [nix].template to be set. See ADR 008."
        ),
    )

    @model_validator(mode="after")
    def validate_domains_vs_env_hostname(self) -> Hop3TomlSchema:
        if self.domains is not None and self.env and "HOST_NAME" in self.env:
            msg = (
                "HOST_NAME cannot be set in [env] when [domains] is also "
                "declared. Move the hostnames into [domains].list and "
                "remove HOST_NAME from [env]."
            )
            raise ValueError(msg)
        return self

    @field_validator("ports")
    @classmethod
    def _validate_unique_ports(
        cls, v: list[PortDeclaration] | None
    ) -> list[PortDeclaration] | None:
        if v:
            seen = [(p.number, p.protocol) for p in v]
            if len(seen) != len(set(seen)):
                msg = "Duplicate (number, protocol) entry in [[ports]]"
                raise ValueError(msg)
        return v

    @field_validator("volumes")
    @classmethod
    def _validate_unique_volumes(
        cls, v: list[VolumeSection] | None
    ) -> list[VolumeSection] | None:
        if v:
            names = [vol.name for vol in v]
            if len(names) != len(set(names)):
                msg = "Duplicate [[volumes]] name"
                raise ValueError(msg)
        return v

    @field_validator("contexts")
    @classmethod
    def validate_context_names(
        cls, v: dict[str, ContextSection] | None
    ) -> dict[str, ContextSection] | None:
        # Pydantic doesn't validate dict keys natively for typed-value dicts.
        # Running the check as a field_validator (rather than a model_validator)
        # means a bad name (`[contexts.has spaces]`) surfaces with `contexts`
        # in the error path, not an empty loc — operators reading the error
        # message get a breadcrumb to the offending section.
        if v is None:
            return v
        for name in v:
            _validate_context_name(name)
        return v

    @field_validator("env")
    @classmethod
    def _validate_env_values(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        # The env value type stays dict[str, Any] (TOML scalars + the `computed`
        # sub-table + `_policy` sentinel), but every *table* value must be a
        # recognised typed form — a generated secret or a reference (ADR 046).
        # Classifying here is the single source of truth and fails loud on an
        # unknown shape instead of silently dropping it.
        if not v:
            return v
        for name, value in v.items():
            if (
                name == "computed"
                or name.startswith("_")
                or not isinstance(value, dict)
            ):
                continue
            if "generate" in value:
                model: type[BaseModel] = EnvGenerate
            elif "from" in value or "key" in value or "external_ip" in value:
                model = EnvRef
            else:
                msg = (
                    f"[env].{name}: unrecognised table value. Use a scalar, a "
                    f"generated secret ({{ generate = ... }}), or a reference "
                    f"({{ from = ..., key = ... }} / {{ external_ip = true }})."
                )
                raise ValueError(msg)
            try:
                model.model_validate(value)
            except ValidationError as e:
                detail = e.errors()[0].get("msg", "invalid value")
                msg = f"[env].{name}: {detail}"
                raise ValueError(msg) from None
        return v


class Hop3TomlValidationError(Exception):
    """Raised when hop3.toml validation fails."""

    def __init__(self, errors: list[dict[str, Any]], raw_data: dict[str, Any]) -> None:
        self.errors = errors
        self.raw_data = raw_data
        self.message = self._format_message()
        super().__init__(self.message)

    def _format_message(self) -> str:
        """Format validation errors into a user-friendly message."""
        lines = ["Invalid hop3.toml configuration:"]

        for error in self.errors:
            loc = " -> ".join(str(x) for x in error.get("loc", []))
            msg = error.get("msg", "Unknown error")
            error_type = error.get("type", "")

            if error_type == "extra_forbidden":
                # Make "extra fields not permitted" errors more helpful
                lines.append(f"  - Unknown field '{loc}'")
                lines.append("    Did you mean one of the valid options?")
            else:
                lines.append(f"  - {loc}: {msg}")

        # Add hint for common mistakes
        if any("extra_forbidden" in str(e.get("type", "")) for e in self.errors):
            lines.append("")
            lines.append("Hint: Check the hop3.toml reference for valid fields:")
            lines.append("  https://hop3.cloud/reference/config/")

        return "\n".join(lines)


def validate_hop3_toml(data: dict[str, Any]) -> Hop3TomlSchema:
    """Validate hop3.toml data against the schema.

    Args:
        data: Parsed TOML data as dictionary

    Returns:
        Validated Hop3TomlSchema instance

    Raises:
        Hop3TomlValidationError: If validation fails with detailed error info
    """
    try:
        return Hop3TomlSchema.model_validate(data)
    except ValidationError as e:
        # Cast ErrorDetails to dict[str, Any] for our error handler
        errors = cast("list[dict[str, Any]]", e.errors())
        raise Hop3TomlValidationError(errors, data) from None
