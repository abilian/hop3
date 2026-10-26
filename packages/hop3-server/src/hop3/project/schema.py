# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Pydantic schema for hop3.toml validation.

This module defines Pydantic models that validate hop3.toml configuration files.
The schema enforces:
- Known sections only (unknown sections are rejected)
- Correct types for all fields
- Valid values where applicable

When validation fails, clear error messages are provided to help users
fix their configuration.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    ValidationError,
    field_validator,
    model_validator,
)

from hop3.core.roles import Role


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
    static_dir: str | None = Field(
        default=None,
        alias="static-dir",
        description=(
            "Directory a static site serves (toolchain = 'static'), relative to "
            "the app root — e.g. 'site', 'html', 'dist'. The first-class, "
            "Procfile-free way to point a static app at its content; defaults to "
            "'public' when unset."
        ),
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
    packages: list[str] | None = Field(
        default=None,
        description="System packages required for build",
    )
    document_root: str | None = Field(
        default=None,
        alias="document-root",
        description=(
            "The directory the web server serves for a PHP app, relative to "
            "the project root. Only needed when it is not detected: a front "
            "controller in public/, web/, htdocs/ or www/ is found "
            "automatically, and the project root is the fallback. Declaring "
            "the wrong root publishes the application's own source, so this "
            "is refused at build time when the path is not a directory."
        ),
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


class DeploySection(BaseModel):
    """[deploy] section - Deploy-time (runtime) configuration."""

    model_config = ConfigDict(extra="forbid")

    deployer: str | None = Field(
        default=None,
        description=(
            "Force a specific deployer instead of auto-selecting by artifact "
            "kind: 'uwsgi', 'static', 'docker-compose', or 'auto' (default). "
            "Unknown names are rejected at deploy time against the installed "
            "deployers."
        ),
    )
    allow_http: bool = Field(
        default=False,
        alias="allow-http",
        description=(
            "Serve the app over plain HTTP as well as HTTPS. Off by default: "
            "Hop3 redirects HTTP to HTTPS, because an app told it is served "
            "over HTTPS issues Secure session/CSRF cookies that a browser will "
            "not send back over HTTP — logins then fail with no usable error. "
            "Enable only for an app that must answer on HTTP (the ACME "
            "challenge path stays on HTTP either way)."
        ),
    )


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
    contains: str | None = Field(
        default=None,
        description=(
            "Expected substring in the health-check response body. When set, the "
            "app counts as ready only once the endpoint returns a body containing "
            "it — a status-only 200 can be a placeholder, an error page, or "
            "another app's default_server content."
        ),
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
    """
    [domains] section - First-class declaration of an app's hostnames.

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
    """
    A single [[ports]] entry — one fixed network port the app binds directly.

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
    source: str = Field(
        default="any",
        description=(
            "Who may reach the port: 'any' (the whole internet, default) or an "
            "IPv4 CIDR (e.g. '10.0.0.0/8') to restrict it to a network. IPv6 "
            "sources are not supported yet."
        ),
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

    @field_validator("source")
    @classmethod
    def _check_source(cls, v: str) -> str:
        # Mirror rootd's validate_source (hop3_rootd.validation): "any" or a
        # canonical IPv4 CIDR; IPv6 unsupported in v1. Validating here fails a
        # bad source at hop3.toml parse time rather than at the rootd boundary
        # mid-deploy. Canonicalise so '10.0.0.5/24' is stored as '10.0.0.0/24'.
        if v == "any":
            return v
        try:
            net = ipaddress.ip_network(v, strict=False)
        except (ValueError, TypeError) as e:
            msg = f"[[ports]] source {v!r} is not a valid CIDR or 'any' ({e})"
            raise ValueError(msg) from None
        if net.version == 6:
            msg = f"[[ports]] source {v!r}: IPv6 sources are not supported yet"
            raise ValueError(msg)
        return str(net)


class TestValidation(BaseModel):
    """
    A single [[test.validations]] entry — one HTTP check the test harness
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
    """
    [test] section — test-harness-specific fields.

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
    """
    An `[env]` value the platform generates once on first deploy (ADR 046).

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
    """
    An `[env]` value resolved from a fact at deploy time (ADR 046 §1b).

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


# Volume types for `[[volumes]]` (ADR 046 §2). "persist" and "scratch" are
# implemented; tmpfs/bind need privileged mounts and fail loud at deploy until then.
VOLUME_TYPES: frozenset[str] = frozenset({"persist", "scratch", "tmpfs", "bind"})

_VOLUME_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class VolumeBackupSection(BaseModel):
    """
    `[volumes.backup]` — per-volume backup policy (ADR 046 §2/§4a).

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
    """
    A `[[volumes]]` entry — a path the app writes, kept outside `src/`.

    Every deploy replaces `src/`. ``persist`` (the default) links ``target`` —
    a directory inside the app's source tree — to storage under
    `<app>/volumes/<name>/`, so writes outlive the redeploy and are backed up.
    ``scratch`` links it to `<app>/scratch/<name>/`, reset from what the source
    ships on every deploy and never backed up: for caches a new version of the
    app must not inherit.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description="Logical volume name; storage lives at <app>/volumes/<name>.",
    )
    target: str = Field(
        description="Directory inside the app tree to back with the volume (relative).",
    )
    type: str = Field(
        default="persist",
        description="persist (default) | scratch | tmpfs | bind.",
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

    @model_validator(mode="after")
    def _check_no_backup_for_scratch(self) -> VolumeSection:
        # A scratch volume is emptied on every deploy; a backup policy on one
        # promises something the platform will never do.
        if self.backup is not None and self.type == "scratch":
            msg = (
                f"[[volumes]] {self.name!r}: a scratch volume is reset on every "
                "deploy and never backed up; remove [volumes.backup], or use "
                "type = 'persist' if its contents must be kept."
            )
            raise ValueError(msg)
        return self


_MEMORY_RE = re.compile(r"^\d+[KMGkmg]?$")


class LimitsSection(BaseModel):
    """
    [limits] section — per-app resource caps (ADR 046 §3).

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


# Request body size: a positive integer with an optional K/M/G suffix — the
# shape every proxy accepts, and the same spelling as [limits] memory so a
# packager learns it once. "0" means no limit.
_BODY_SIZE_RE = re.compile(r"^\d+[KMGkmg]?$")
# One segment of a [proxy] deny path: the unreserved URL characters, so an
# entry cannot smuggle a regex, a space or a quote into the proxy's config.
_DENY_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._~-]+$")


class ProxySection(BaseModel):
    """
    [proxy] section — what the reverse proxy will carry for this app.

    The proxy is platform-owned and stays that way: this is not a passthrough
    for proxy config. It declares what is a property of the *app* rather than
    of the platform: how large a request body it accepts, whether that body
    may stream through instead of being spooled to the proxy's disk first, and
    which paths must never be answered at all. An app that receives file uploads has to be able to
    say so; before this section existed, a 50 MB ceiling applied to every app
    on the box and nothing could lift it.

    Each key renders to the active proxy's own directive (nginx
    ``client_max_body_size`` / ``proxy_request_buffering``, Caddy
    ``request_body max_size``, Traefik a ``buffering`` middleware), so the
    declaration outlives a proxy swap.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    max_body_size: str | None = Field(
        default=None,
        alias="max-body-size",
        description=(
            "Largest request body the proxy accepts, e.g. '2G' (default "
            "'50m', '0' for no limit). A larger upload is refused by the "
            "proxy before the app sees it, so the app cannot report the error "
            "itself."
        ),
    )
    # StrictBool: TOML has real booleans, and a lax bool would read the
    # string "off" as False here while Hop3Config.proxy_request_buffering,
    # which reads the raw TOML, reads the same string as True. One field, two
    # readers, opposite answers — so only a real boolean is accepted.
    request_buffering: StrictBool | None = Field(
        default=None,
        alias="request-buffering",
        description=(
            "Whether the proxy reads the whole request body before the app "
            "sees any of it (default true). Set false for large uploads: the "
            "body streams through, the proxy needs no scratch space for it, "
            "and the app's first byte arrives with the client's first byte."
        ),
    )

    deny: tuple[str, ...] = Field(
        default=(),
        description=(
            "URL paths the proxy answers with 404, each with everything "
            "beneath it, e.g. ['/data', '/storage']. For data an app keeps "
            "inside the tree it serves, which upstream protects with an "
            ".htaccess that only Apache reads."
        ),
    )

    @field_validator("deny")
    @classmethod
    def _check_deny(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_deny_path(path) for path in v)

    @field_validator("max_body_size")
    @classmethod
    def _check_max_body_size(cls, v: str | None) -> str | None:
        if v is not None and not _BODY_SIZE_RE.match(v):
            msg = (
                f"[proxy] max-body-size {v!r} must be a number with an "
                "optional K/M/G suffix, e.g. '50m', '2G', or '0' for no limit."
            )
            raise ValueError(msg)
        return v


def _deny_path(path: str) -> str:
    """A [proxy] deny entry in its one spelling: ``/data``, no trailing slash."""
    segments = path.removeprefix("/").removesuffix("/").split("/")
    valid = path.startswith("/") and all(
        _DENY_SEGMENT_RE.match(segment) and segment not in {".", ".."}
        for segment in segments
    )
    if not valid:
        msg = (
            f"[proxy] deny entry {path!r} must be a URL path below the root, "
            "such as '/data' or '/app/storage': a leading '/', then segments "
            "of letters, digits, '.', '_', '~' or '-'."
        )
        raise ValueError(msg)
    return "/" + "/".join(segments)


# WAF (ADR 050) — Layer-7 Web Application Firewall config. Engine-independent
# declarative surface; the platform compiles it to the engine's native form
# (SecLang for LeWAF) at deploy time.

_WAF_MODES: frozenset[str] = frozenset({"block", "detect"})
# Ban window/duration: a positive integer with a unit suffix, e.g. "30s", "10m",
# "1h", "24h". Kept deliberately small — no compound durations.
_WAF_DURATION_RE = re.compile(r"^[1-9]\d*[smhd]$")


def _check_path_regex(pattern: str, section: str = "[waf]") -> str:
    """
    Validate one access-path pattern: a non-empty, compilable regex.

    Patterns are full-matched against the canonical request path at runtime
    (ADR 050 §2 / Security invariant 2). Here we only guarantee the pattern is
    a valid regex so a typo fails at deploy, not at request time. ReDoS bounding
    (invariant 8) is a runtime concern, not enforced here.
    """
    if not pattern or pattern != pattern.strip():
        msg = f"{section} path pattern must be a non-empty regex without surrounding whitespace"
        raise ValueError(msg)
    if '"' in pattern:
        # Patterns are embedded in a double-quoted SecLang operator argument; a
        # literal quote could terminate it and inject directives/actions
        # (Security invariant 6). A URL-path regex never needs one — reject at
        # the trust boundary so the compiler needs no fragile escaping.
        msg = f'{section} path pattern {pattern!r} must not contain a double quote (")'
        raise ValueError(msg)
    try:
        re.compile(pattern)
    except re.error as e:
        msg = f"{section} path pattern {pattern!r} is not a valid regex: {e}"
        raise ValueError(msg) from None
    return pattern


class WafGate(BaseModel):
    """
    A ``[[waf.gate]]`` entry — conditional access (ADR 050 §2, use case 2).

    Matching paths are reachable only when ``require`` holds: a named network
    (operator-defined, resolved at deploy from the DB). Authentication is not a
    gate condition: ``[access]`` expresses it (ADR 062), and ``auth`` here is
    refused with a message pointing there.
    """

    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(
        description="URL-path regexes (full-matched) this gate covers."
    )
    require: str = Field(
        description="Condition: a named network.",
    )

    @field_validator("paths")
    @classmethod
    def _check_paths(cls, v: list[str]) -> list[str]:
        if not v:
            msg = "[[waf.gate]] needs at least one path pattern"
            raise ValueError(msg)
        return [_check_path_regex(p) for p in v]

    @field_validator("require")
    @classmethod
    def _check_require(cls, v: str) -> str:
        if v == "auth":
            msg = (
                "[[waf.gate]] requires a named network. To put the app behind a "
                'Hop3 sign-in, use [access] require = "auth" (ADR 062).'
            )
            raise ValueError(msg)
        if not v or v != v.strip():
            msg = (
                "[[waf.gate]] require must be a named network (non-empty, no "
                "surrounding whitespace)."
            )
            raise ValueError(msg)
        return v


class WafTuning(BaseModel):
    """
    A ``[[waf.tuning]]`` entry — scoped CRS false-positive relief (ADR 050 §3).

    Verb-named keys (``disable-rule-ids`` / ``skip-body-inspection``) so the
    direction is unambiguous (never the old "exclusions"). Scoped to ``paths``;
    omit ``paths`` for a global entry.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    paths: list[str] | None = Field(
        default=None,
        description="Path regexes to scope this tuning to; omit for global.",
    )
    disable_rule_ids: list[int] | None = Field(
        default=None,
        alias="disable-rule-ids",
        description="CRS rule IDs to turn off (within the scope).",
    )
    skip_body_inspection: bool = Field(
        default=False,
        alias="skip-body-inspection",
        description="Don't scan request bodies (within the scope).",
    )
    reason: str | None = Field(
        default=None,
        description="Why the relief is needed — surfaced for audit.",
    )

    @field_validator("paths")
    @classmethod
    def _check_paths(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if not v:
            msg = "[[waf.tuning]] paths, if present, must be non-empty"
            raise ValueError(msg)
        return [_check_path_regex(p) for p in v]

    @model_validator(mode="after")
    def _check_does_something(self) -> WafTuning:
        # A tuning entry that disables nothing is a no-op typo; reject it so a
        # mistaken `disabled-rule-ids` key (silently dropped by alias) is caught.
        if not self.disable_rule_ids and not self.skip_body_inspection:
            msg = (
                "[[waf.tuning]] must set 'disable-rule-ids' and/or "
                "'skip-body-inspection' — an entry that relaxes nothing is a typo."
            )
            raise ValueError(msg)
        return self


class WafBans(BaseModel):
    """The ``[waf.bans]`` table — repeat-offender throttling (ADR 050 §4)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False)
    threshold: int = Field(
        default=5, description="Violations within the window before a ban."
    )
    window: str = Field(default="10m", description="Scoring window, e.g. '10m'.")
    duration: str = Field(default="1h", description="Ban TTL, e.g. '1h', '24h'.")

    @field_validator("threshold")
    @classmethod
    def _check_threshold(cls, v: int) -> int:
        if v < 1:
            msg = f"[waf.bans] threshold must be >= 1, got {v}"
            raise ValueError(msg)
        return v

    @field_validator("window", "duration")
    @classmethod
    def _check_duration(cls, v: str) -> str:
        if not _WAF_DURATION_RE.match(v):
            msg = (
                f"[waf.bans] duration {v!r} must be a positive integer with a unit "
                "suffix (s/m/h/d), e.g. '30s', '10m', '1h', '24h'."
            )
            raise ValueError(msg)
        return v


class WafSection(BaseModel):
    """
    The ``[waf]`` section — per-app Layer-7 WAF policy (ADR 050).

    Two access constructs (ADR 050 §2): ``allow`` (a positive allowlist that, when
    present, denies everything else — use case 1) and ``[[waf.gate]]`` (conditional
    access — use case 2). ``[[waf.tuning]]`` relaxes CRS false positives; ``[waf.bans]``
    throttles repeat offenders. Off by default (``enabled = false``).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False)
    mode: str = Field(default="block", description="'block' or 'detect' (log-only).")
    ruleset: str = Field(default="owasp-crs", description="CRS baseline ruleset.")
    paranoia: int = Field(default=1, description="CRS paranoia level, 1-4.")
    allow: list[str] | None = Field(
        default=None,
        description=(
            "Positive model: URL-path regexes the app serves. If present, any "
            "path matching none of these (and no satisfied gate) is denied."
        ),
    )
    gate: list[WafGate] | None = Field(
        default=None, description="Conditional-access rules ([[waf.gate]])."
    )
    tuning: list[WafTuning] | None = Field(
        default=None, description="CRS false-positive relief ([[waf.tuning]])."
    )
    bans: WafBans | None = Field(default=None, description="Ban policy ([waf.bans]).")

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        if v not in _WAF_MODES:
            msg = f"[waf] mode {v!r} must be one of: {', '.join(sorted(_WAF_MODES))}"
            raise ValueError(msg)
        return v

    @field_validator("paranoia")
    @classmethod
    def _check_paranoia(cls, v: int) -> int:
        if not 1 <= v <= 4:
            msg = f"[waf] paranoia must be between 1 and 4, got {v}"
            raise ValueError(msg)
        return v

    @field_validator("allow")
    @classmethod
    def _check_allow(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if not v:
            # An empty `allow` would deny *everything* — almost certainly a
            # mistake. Omit the key to disable the positive model instead.
            msg = (
                "[waf] allow, if present, must be non-empty — it enables "
                "default-deny. Remove the key to serve all paths."
            )
            raise ValueError(msg)
        return [_check_path_regex(p) for p in v]


class AccessSection(BaseModel):
    """
    The ``[access]`` section: who may reach the app at all (ADR 062).

    ``require = "auth"`` puts the whole app behind a Hop3 sign-in, checked by
    the proxy before each request. ``role`` is the lowest standard role
    admitted (ADR 061). ``public-paths`` are reachable anonymously: regexes
    full-matched against the normalized path, the grammar of ADR 050 §2.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    require: Literal["auth", "none"] = Field(
        default="none",
        description='"auth": only signed-in Hop3 accounts reach the app.',
    )
    role: Role = Field(
        default=Role.MEMBER,
        description="Lowest standard role admitted: member, viewer, deployer, admin.",
    )
    public_paths: list[str] = Field(
        default_factory=list,
        alias="public-paths",
        description="Path regexes reachable without signing in (webhooks, health).",
    )

    @field_validator("role", mode="before")
    @classmethod
    def _parse_role(cls, v: object) -> object:
        # Parsed once, here, with Role's own message for an unknown name: it was
        # parsed, turned back into a string, and parsed again by the deployer.
        return Role.parse(v) if isinstance(v, str) else v

    @field_validator("public_paths")
    @classmethod
    def _check_public_paths(cls, v: list[str]) -> list[str]:
        return [_check_path_regex(p, "[access]") for p in v]


# Context names appear unquoted on the CLI and as TOML keys; keep them
# shell-friendly. Same shape as the CLI validator
# (hop3_cli.commands.local.context_cmd._CONTEXT_NAME_RE).
_CONTEXT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# Committed-credential tripwire (ADR 042, 2nd revision). hop3.toml is secret-free
# by convention; this backs the convention with a LOUD refusal when an obvious
# secret is committed. Best-effort known-shapes, not a proof — high-entropy
# heuristics are deliberately omitted (too many false positives on legit hashes).
_SECRET_PREFIXES = (
    "sk_live_",
    "sk_test_",
    "rk_live_",
    "ghp_",
    "gho_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "AKIA",
    "ASIA",
)
_CREDS_IN_URL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://[^/@\s]*:[^/@\s]+@")


def _secret_reason(value: str) -> str | None:
    """Return a reason if ``value`` looks like a committed secret, else None."""
    if any(value.startswith(p) for p in _SECRET_PREFIXES):
        return "a known API-key prefix"
    if _CREDS_IN_URL.match(value):
        return "a connection string with embedded credentials"
    return None


def _reject_committed_env_secret(name: str, value: object, where: str) -> None:
    """Fail loud if a scalar env value under ``where`` looks like a secret."""
    if isinstance(value, str) and (reason := _secret_reason(value)):
        msg = (
            f"{where}.{name} looks like a credential ({reason}). hop3.toml is "
            "committed and must stay secret-free — set it server-side with "
            "`hop3 env set` instead."
        )
        raise ValueError(msg)


#: ``${VAR}``, with an optional ``:-default`` — the shell spelling a recipe
#: reaches for, and the one a literal `[env]` value does not expand.
#:
#: Bare ``$VAR`` is just as inert in a literal section and is deliberately NOT
#: matched: unlike ``${...}``, a lone ``$`` has legitimate literal uses in these
#: values (an nginx or uWSGI log format carries ``$remote_addr``, a password
#: may contain one), so rejecting it would fail valid recipes. No recipe in
#: either tree writes one today. Widen this only with a rule that can tell the
#: two apart.
_INTERPOLATION = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-[^}]*)?\}")

#: A value that is nothing but a shell reference without braces: `"$PORT"`.
#: Only the whole value: `$` inside a longer value is often meant literally
#: (a prompt, a template the app expands itself), but a value that is exactly
#: `$NAME` was written for a shell that never sees it.
_BARE_REFERENCE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

#: Two facts about interpolation that both the validator (wrong section) and
#: the deploy-time resolver (right section, missing variable) have to state.
#: Kept here, next to the syntax they describe, so the two cannot drift.
PORT_IS_NOT_AN_ENV_VALUE = (
    "$PORT is allocated after every [env] section is resolved, so no env "
    "section can carry it: bind it in [run].start, which runs through a shell "
    'with $PORT exported — e.g. start = "env GF_SERVER_HTTP_PORT=$PORT '
    './bin/grafana-server".'
)

NO_DEFAULT_FORM = (
    "[env.computed] interpolates ${VAR}, but has no ${VAR:-default} form — "
    "write the plain reference there, or expand it in [run].start, where a "
    "shell does support defaults."
)


def _reject_uninterpolated_env_value(name: str, value: object, where: str) -> None:
    """
    Fail loud on a ``${VAR}`` written where nothing will expand it.

    ``[env]`` values are literal: exported verbatim, single-quoted, into the
    app's environment. ``[env.computed]`` is the one that interpolates.
    Writing ``${PGHOST}`` in the wrong section is silent and total — Grafana
    received ``GF_DATABASE_HOST=${PGHOST}:${PGPORT}`` and
    ``GF_SERVER_HTTP_PORT=${PORT:-8080}`` as those exact strings, so it fell
    back to SQLite and to its own port 3000, while Hop3 had provisioned a
    PostgreSQL addon it never opened and pointed the proxy at a port it never
    bound. The deploy read green until the readiness probe timed out.

    The recipe said what it meant; only the section was wrong. Saying so at
    validation catches it in ``hop3check``, before any of that.
    """
    if not isinstance(value, str):
        return
    if bare := _BARE_REFERENCE.fullmatch(value):
        referenced = bare.group(1)
        remedy = _interpolation_remedy(referenced, has_default=False)
        msg = (
            f"{where}.{name} = {value!r} is exported literally: the app receives "
            f"the text {value!r}, not the value of {referenced}. {remedy} "
            f"There, write it as ${{{referenced}}}."
            if referenced != "PORT"
            else f"{where}.{name} = {value!r} is exported literally: the app "
            f"receives the text {value!r}, not a port. {remedy}"
        )
        raise ValueError(msg)
    match = _INTERPOLATION.search(value)
    if not match:
        return
    remedy = _interpolation_remedy(match.group(1), has_default=bool(match.group(2)))
    msg = (
        f"{where}.{name} = {value!r} contains ${{...}}, which {where} does not "
        f"expand — the value is exported literally. {remedy}"
    )
    raise ValueError(msg)


def _interpolation_remedy(referenced: str, *, has_default: bool) -> str:
    """
    Where this particular reference does belong.

    Each of the three answers is a different section, and naming the wrong one
    sends the reader somewhere the value is just as inert.
    """
    if referenced == "PORT":
        return PORT_IS_NOT_AN_ENV_VALUE
    if has_default:
        return NO_DEFAULT_FORM
    return (
        "Move it to [env.computed], which interpolates against the app's "
        "environment after addons are provisioned."
    )


class CliSection(BaseModel):
    """
    The ``[cli]`` block — per-project CLI preferences (ADR 042 §Resolution).

    Client-side only, exactly like ``[contexts.*]``: the CLI reads it while
    resolving which app a command acts on (source #4 of the resolution chain,
    below ``.hop3-app`` and above ``[contexts.<sel>].app``), and the deployer
    ignores it. It is declared here because the schema is ``extra="forbid"``
    and validates the whole committed file — without this block, a project
    that follows the CLI's own documented resolution chain is rejected at
    deploy, which is a contradiction between two halves of the same product
    rather than a config error.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    app: str | None = Field(
        default=None,
        description=(
            "App instance name this project binds to, when it differs from "
            "[metadata].id. Read by the CLI, ignored by the deployer."
        ),
    )

    @field_validator("app")
    @classmethod
    def validate_app(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v or v != v.strip():
            msg = (
                "[cli].app must be a non-empty app name without surrounding "
                "whitespace. Omit it to inherit [metadata].id."
            )
            raise ValueError(msg)
        return v


class ContextSection(BaseModel):
    """
    A single ``[contexts.<name>]`` block (ADR 042).

    What differs for this app when it is deployed through the context
    ``<name>``: the app's name there, its domains, its environment. The block
    never says where the app is deployed: a context is a server in each
    developer's own CLI configuration, and the block applies to whichever
    server that context names. Carries NO secrets: a committed-credential
    tripwire rejects secret-shaped values. Resolved CLIENT-SIDE; the deployer
    ignores ``[contexts.*]``.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    app: str | None = Field(
        default=None,
        description="App instance name for this environment; inherits [metadata].id when absent.",
    )
    domains: DomainsSection | None = Field(
        default=None,
        description=(
            "Hostnames for this environment — same shape as top-level [domains] "
            "(a `list = [...]` table). Full-replaces top-level when present."
        ),
    )
    env: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Non-secret env overrides; merge over top-level [env]. Secrets go "
            "server-side via `hop3 env set`, never here."
        ),
    )

    @field_validator("app")
    @classmethod
    def validate_app(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v or v != v.strip():
            msg = (
                "Context.app must be a non-empty app name without surrounding "
                "whitespace. Omit it to inherit [metadata].id."
            )
            raise ValueError(msg)
        return v

    @field_validator("env")
    @classmethod
    def validate_env_secret_free(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if v:
            for name, value in v.items():
                _reject_committed_env_secret(name, value, "[contexts.*.env]")
                _reject_uninterpolated_env_value(name, value, "[contexts.*.env]")
        return v

    @model_validator(mode="after")
    def validate_domains_vs_env_hostname(self) -> ContextSection:
        if (
            self.domains is not None
            and self.env is not None
            and "HOST_NAME" in self.env
        ):
            msg = (
                "HOST_NAME cannot be set in a context's [env] when the context "
                "also declares `domains`. Keep one or the other."
            )
            raise ValueError(msg)
        return self


class AdminSection(BaseModel):
    """
    [admin] section — an app's initial admin account (ADR 056).

    The platform generates the password once (CSPRNG, stable across redeploy),
    resolves the email, injects a canonical ``HOP3_ADMIN_USER`` /
    ``HOP3_ADMIN_EMAIL`` / ``HOP3_ADMIN_PASSWORD`` triple into the app's runtime
    env, records the credential (encrypted, retrievable via ``hop3 app
    credentials``), and runs ``create`` once post-deploy to create the account.
    The recipe maps the canonical vars to whatever its app expects.
    """

    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(
        default=None,
        description="Login username; omit when the app keys admins by email.",
    )
    email: str | None = Field(
        default=None,
        description=(
            "Admin email: 'operator' -> the server's OPERATOR_EMAIL, or a "
            "literal address. Omit when the app needs no admin email."
        ),
    )
    password: EnvGenerate = Field(
        description=(
            "How to generate the admin password. Always generated (never a "
            "literal), so no credential is committed to the recipe."
        ),
    )
    create: str | None = Field(
        default=None,
        description=(
            "Idempotent (create-if-absent) command run once post-deploy to "
            "create the account. Receives HOP3_ADMIN_USER/EMAIL/PASSWORD in its "
            "environment. Omit when the app bootstraps itself from those vars."
        ),
    )
    verify: str | None = Field(
        default=None,
        description=(
            "Command proving the account actually exists, run right after "
            "`create` and required to exit 0. Needed because a bootstrap CLI "
            "can print an error and still exit 0 — Gitea and Forgejo reject "
            "the reserved name 'admin' exactly that way — so `create`'s exit "
            "status is not evidence the account was made. Without this Hop3 "
            "reports only that the command ran, never that the account exists."
        ),
    )
    login: Literal["username", "email"] | None = Field(
        default=None,
        description=(
            "Which identifier the app's sign-in form takes. Only the recipe "
            "knows: BookStack authenticates by email while its username is just "
            "a display name, so an operator handed both credentials picks wrong "
            "and is rejected. Omit only when the app declares just one of them."
        ),
    )

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        if v is None or v == "operator":
            return v
        # A literal address must look like one (not a bare "@").
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            msg = (
                f"[admin].email {v!r} must be 'operator' (use the server's "
                "OPERATOR_EMAIL) or a literal email address."
            )
            raise ValueError(msg)
        return v

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            msg = "[admin].username must not be blank."
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _needs_an_identity(self) -> AdminSection:
        if not self.username and not self.email:
            msg = "[admin] needs at least one of `username` or `email`."
            raise ValueError(msg)
        # Pointing `login` at an identifier the recipe never declares would hand
        # the operator a sign-in field that stays empty — fail at parse time.
        if self.login == "username" and not self.username:
            msg = "[admin].login = 'username' but no `username` is declared."
            raise ValueError(msg)
        if self.login == "email" and not self.email:
            msg = "[admin].login = 'email' but no `email` is declared."
            raise ValueError(msg)
        return self


class ProbeSection(BaseModel):
    """
    [probe] section — a Hop3-owned account used to verify the app keeps working.

    The [admin] credential is handed to the operator, so Hop3 stops owning it the
    moment they change the password: a later sign-in failure could equally mean
    the app broke or the password moved, and from outside those are the same
    observation. A probe account nobody else uses removes that ambiguity — its
    password is Hop3's to rotate, so a failed probe sign-in means the app broke.

    It exists to exercise the FULL dynamic path — app code, session, database,
    password verification — which no unauthenticated request reaches: a login
    page renders fine with a dead database, and may not even be dynamic.

    Deliberately NOT an administrator: signing in is the entire diagnostic value,
    and a plain account carries a fraction of the privilege. Omit the section
    entirely for an app whose data is sensitive enough that no standing Hop3
    account is acceptable — the check then verifies the handover only, and says
    so rather than silently testing less.
    """

    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        default="hop3probe",
        description=(
            "Login name for the probe account. Avoid names an app reserves "
            "(Gitea and Forgejo reject 'admin', while still exiting 0)."
        ),
    )
    email: str | None = Field(
        default=None,
        description=(
            "Email for the probe account, when the app requires one. A literal "
            "address; unlike [admin].email this is never the operator's, since "
            "the account is Hop3's and receives nothing."
        ),
    )
    create: str = Field(
        description=(
            "REQUIRED. Idempotent (create-if-absent) command that creates the "
            "account. Receives HOP3_PROBE_USER/EMAIL/PASSWORD in its "
            "environment, runs after the app is up, and must exit non-zero if "
            "the account does not end up existing."
        ),
    )
    verify: str | None = Field(
        default=None,
        description=(
            "Command proving the probe account exists, run after `create` and "
            "required to exit 0. `create` is documented as having to exit "
            "non-zero on failure, but that is a promise the app's own CLI "
            "makes and some break it (Gitea and Forgejo print an error and "
            "exit 0 for the reserved name 'admin'). Declare this and the "
            "'account exists' marker rests on evidence rather than on an app "
            "keeping that promise."
        ),
    )

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        if not v.strip():
            msg = "[probe].username must not be blank."
            raise ValueError(msg)
        return v

    @field_validator("create")
    @classmethod
    def _check_create(cls, v: str) -> str:
        """
        A probe Hop3 cannot create is a probe Hop3 cannot trust.

        `create` used to be optional, meaning "the app makes this account itself
        from the injected vars". Hop3 has no way to confirm that it did, so the
        smoke test could not be given the credential — which made the whole
        section inert: it read as configuration and did nothing at all.

        The two recipes that used the form both proved the point. matomo's
        installer and uptime-kuma's bootstrap each created the probe only in the
        branch where they also created the ADMIN, so any instance that already
        had one silently got no probe — undetectable, because nothing ever
        checked. Declaring the section must mean the account exists, and the
        only way Hop3 knows that is by running a command and watching it
        succeed.
        """
        if not v.strip():
            msg = (
                "[probe].create must not be blank. It is the command Hop3 runs "
                "to create the probe account; without one, Hop3 cannot know the "
                "account exists and the section would do nothing."
            )
            raise ValueError(msg)
        return v


class Hop3TomlSchema(BaseModel):
    """
    Complete hop3.toml schema with validation.

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
    deploy: DeploySection | None = None
    run: RunSection | None = None
    env: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Environment variables. A value is a scalar, or one of three typed "
            "tables (ADR 046): { generate = 'hex' | 'base64' | 'urlsafe' | "
            "'password' | 'uuid', length = N } for a secret minted once on "
            "first deploy; { from = '<addon>', key = '<VAR>' } or "
            "{ key = 'domain' } for a value copied from an addon or an app "
            "fact; and the [env.computed] sub-table, whose values are ${VAR} "
            "templates interpolated against the app's env AFTER addons are "
            "provisioned — the way to expose an addon's DATABASE_URL under the "
            "name an app expects. Set _policy = 'override' to update existing "
            "values on redeploy. Typed as free-form because the three forms "
            "and the sub-table share one namespace; the validator below is "
            "what actually constrains it."
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
    probe: ProbeSection | None = Field(
        default=None,
        description=(
            "A Hop3-owned account for verifying the app keeps working, whose "
            "password Hop3 controls (see ProbeSection)."
        ),
    )
    admin: AdminSection | None = Field(
        default=None,
        description=(
            "Initial admin account to bootstrap on first deploy (ADR 056). The "
            "platform generates the password, creates the account, and surfaces "
            "the credential to the operator."
        ),
    )
    addons: list[AddonConfig] | None = None
    contexts: dict[str, ContextSection] | None = Field(
        default=None,
        description=(
            "What differs per deployment (ADR 042), keyed by context name: "
            "each [contexts.<name>] holds the app's name, domains and env when "
            "it is deployed through that context. Never a server address. "
            "Non-secret; resolved client-side; ignored by the deployer."
        ),
    )
    cli: CliSection | None = Field(
        default=None,
        description=(
            "Per-project CLI preferences (ADR 042). Currently just `app`, the "
            "app name this project binds to. Non-secret; resolved client-side; "
            "ignored by the deployer."
        ),
    )
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
    proxy: ProxySection | None = Field(
        default=None,
        description=(
            "Per-app reverse-proxy transfer limits: max-body-size and "
            "request-buffering. Rendered into whichever proxy is active."
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
    access: AccessSection | None = Field(
        default=None,
        description=(
            'Who may reach the app (ADR 062): require = "auth" puts it behind '
            "a Hop3 sign-in, with a minimum role and anonymous public paths."
        ),
    )
    waf: WafSection | None = Field(
        default=None,
        description=(
            "Layer-7 Web Application Firewall policy (ADR 050): positive "
            "allowlist / conditional gates, CRS tuning, and bans. Off unless "
            "[waf].enabled = true."
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

    @field_validator("contexts", mode="before")
    @classmethod
    def _refuse_a_context_address(cls, v: object) -> object:
        """
        ``server`` and ``bootstrap`` moved to the CLI's contexts (ADR 042).

        Named, rather than left to ``extra="forbid"``, so the refusal says
        what replaces them.
        """
        if not isinstance(v, dict):
            return v
        for name, block in v.items():
            if not isinstance(block, dict):
                continue
            for key in ("server", "bootstrap"):
                if key in block:
                    msg = (
                        f"[contexts.{name}] no longer takes {key!r}: hop3.toml does "
                        "not say where the app is deployed. Record the server as a "
                        f"context of your own (`hop3 context add {name} --server "
                        f"<address>`) and remove {key!r} from the block."
                    )
                    raise ValueError(msg)
        return v

    @field_validator("contexts")
    @classmethod
    def _validate_context_names(
        cls, v: dict[str, ContextSection] | None
    ) -> dict[str, ContextSection] | None:
        if v:
            for name in v:
                if not _CONTEXT_NAME_RE.match(name):
                    msg = (
                        f"Invalid context name {name!r}. Names start with a "
                        "letter or digit, then letters/digits/'-'/'_', max 64 chars."
                    )
                    raise ValueError(msg)
        return v

    @field_validator("env")
    @classmethod
    def _validate_env_values(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        # The env value type stays dict[str, Any] (TOML scalars + the `computed`
        # sub-table + `_policy` sentinel), but every *table* value must be a
        # recognised typed form — a generated secret or a reference (ADR 046).
        # Classifying here is the single source of truth and fails loud on an
        # unknown shape instead of silently dropping it. Scalar string values are
        # scanned by the committed-credential tripwire (ADR 042 r2).
        if not v:
            return v
        for name, value in v.items():
            if name == "computed" or name.startswith("_"):
                continue
            if not isinstance(value, dict):
                _reject_committed_env_secret(name, value, "[env]")
                _reject_uninterpolated_env_value(name, value, "[env]")
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
    """
    Validate hop3.toml data against the schema.

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
