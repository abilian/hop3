# ADR 019: Basic Commands for the Hop3 Command-Line

**Status**: Accepted
**Type**: Feature
**Created**: 2024-07-17
**Updated**: 2026-06-16
**Related-ADRs**: 018, 025, 031, 036

## Revisions

- v0.4 (2026-06-16): Renamed the "Marketplace" command family to "Catalog" to match the ratified terminology in ADR 031 (the free, self-host app collection is the "Catalog"; "Marketplace" is reserved for the future commercial product).
- v0.3: Recorded that the shipped command surface is wider than the original spec — the original spec was a kernel, not a ceiling — and documented which originally-specified commands remain deferred and why (2026-04-14).
- v0.2: Status promoted to Accepted with implementation status block.
- v0.1: Initial draft (2024-07-17)

## Implementation Status

The shipped CLI covers and extends the originally-specified command set. The dispatch mechanism lives in `hop3/commands/`, with the `@register` decorator scanning all command modules at startup.

### Shipped command families

| Family | Commands (selected) | Role |
|--------|---------------------|------|
| **Auth** | `auth:login`, `auth:logout`, `auth:register`, `auth:magic-link` | Session management. |
| **App** | `app:deploy`, `app:start`, `app:stop`, `app:restart`, `app:destroy`, `app:logs`, `app:run`, `app:env:*` | Full application lifecycle. |
| **System** | `system:status`, `system:info`, `system:check`, `system:ssh` | Host-level inspection and shell access. |
| **Addon** | `addon:create`, `addon:destroy`, `addon:list`, per-addon flows | Backing-service lifecycle. |
| **Backup** | `backup:create`, `backup:list`, `backup:restore`, `backup:delete` | Per ADR 024. |
| **Admin** | `admin:create-user`, `admin:reset-password`, `admin:delete-user` | Operator provisioning (server-side entry points per ADR 014). |
| **Server** | `server:setup`, `server:update` | Hop3-server lifecycle on the host. |
| **Health** | `healthcheck`, `healthcheck:debug` | Diagnostic commands. |
| **Nix** | `nix:eject` | Template-generated → hand-crafted `hop3.nix` (ADR 008). |

The `hop3` CLI aliases `hop` for brevity. Full command listing: `hop3 --help`.

### Originally-specified but not shipped

| Command | Status | Reason |
|---------|--------|--------|
| `build` (separate from deploy) | Deferred | Builds are currently tied to deploy. A stand-alone `build` command would be cheap to add; it is not requested by operators. |
| `revert` | Scheduled with ADR 032 (deployment-strategies / artefact-lifecycle). Requires versioned artefacts. |
| `new` (project scaffolding) | Candidate | Low priority; operators adopt Hop3 by adding a `hop3.toml` to an existing repo, not by generating one. |
| `docker` (run Docker on server) | Out of scope | The server-side SSH shell covers this without a dedicated CLI wrapper. |
| `upgrade` / `downgrade` | Scheduled with ADR 032 |
| Catalog commands (`search`, `info`, `install`) | Deferred | The catalog subsystem (`server/catalog/`, web UI only) has no CLI surface yet; the commands follow the web work. |

### Ergonomics and help system

CLI ergonomics — help text, discoverability, error messages — are covered separately in ADR 036.

## Introduction

This ADR outlines the basic commands for the Hop3 command-line interface (CLI), which serves as the primary tool for interacting with the Hop3 platform. The CLI is designed to be simple and user-friendly, delegating most logic and formatting responsibilities to the server.

## Summary

The Hop3 CLI will support a range of commands for user authentication, application management, system status, and service operations. The commands are designed to be intuitive and cater to the needs of developers, sysadmins, and end-users. The CLI will rely on the server to handle business logic and formatting, ensuring a lightweight client that is easy to maintain.

## Context and Goals

### Context

The Hop3 project aims to provide a self-hosted PaaS solution that simplifies the deployment and management of web applications. To facilitate this, an efficient and user-friendly CLI is essential. The CLI should be capable of performing various tasks related to application management, system status checks, and service operations.

### Goals

- Design a comprehensive set of commands for the Hop3 CLI.
- Ensure the CLI is user-friendly and intuitive.

## Decision

The Hop3 CLI will implement a set of commands categorized into Authentication, Catalog, Development, System-Level Operations, App-Level Operations, and Service Operations. These commands will interact with the server using JSON-RPC over HTTPS.

## Basic Commands

### Authentication

- `hop3 login`: Log in to the Hop3 server.
- `hop3 logout`: Log out from the Hop3 server.

Credentials are stored in `~/.hop3/credentials.toml` or similar, and may also be provided by environment variables (e.g., `HOP3_TOKEN`, `HOP3_LOGIN`, `HOP3_PASSWORD`, `HOP3_SERVER_URI`).

### Development

- `hop3 new`: Start a new project/package.
- `hop3 build`: Build the current package.
- `hop3 deploy`: Deploy the current project.
- `hop3 revert`: Revert a failed deployment.

### System-Level Operations

- `hop3 status`: Get the general status of the system.
- `hop3 ssh`: SSH into the Hop3 server.
- `hop3 docker`: Run a Docker command.

### App-Level Operations

- `hop3 apps`: List all running apps (or app instances).
- `hop3 start|stop|restart <app>`: Start, stop, or restart an app.
- `hop3 destroy <app>`: Destroy an app and its associated data.
- `hop3 backup <app>`: Run a backup for an app.
- `hop3 upgrade <app>`: Upgrade an app.
- `hop3 downgrade <app>`: Downgrade an app (if applicable).
- `hop3 logs <app>`: Stream logs for an app (similar to `tail -f`).
- `hop3 env list|set|unset <app>`: Manipulate environment variables for an app.
- `hop3 run <app> <command>`: Run a one-shot command for an app.

### Service Operations

- `hop3 services`: List services (databases, etc.).
- `hop3 service status|start|stop <service>`: Manage services (e.g., databases).
- `hop3 pg|mysql|redis|mongo <command>`: Specific commands for database services (including access to shell).

### Catalog

- `hop3 search`: Search the catalog for available apps (name + short description).
- `hop3 info`: Get detailed information on a specific app from the catalog.
- `hop3 install`: Install (or instantiate) an app from the catalog.

## Related

- CLI commands overview [ADR-018](./018-cli-architecture.md)

## Open Questions

Do we call the command `hop3` or just `hop`?
