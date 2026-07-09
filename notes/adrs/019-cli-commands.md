# ADR 019: Basic Commands for the Hop3 Command-Line

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2024-07-17
- **Updated**: 2026-06-23
- **Related-ADRs**: [018](./018-cli-architecture.md), [025](./025-cli-user-experience.md), [031](./031-project-terminology.md), [036](./036-cli-ergonomics.md), [042](./042-cli-context-model.md)

## Command surface

The command set specified here is a kernel: the CLI may expose a wider surface than the families listed below. The dispatch mechanism lives in `hop3/commands/`, with the `@register` decorator scanning all command modules at startup.

The app collection the catalog commands address is the "Catalog": the free, self-hostable app collection ([ADR 031](./031-project-terminology.md)). "Marketplace" is reserved for the future commercial product and is not a CLI command family.

### Command families

| Family | Commands (selected) | Role |
|--------|---------------------|------|
| **Auth** | `auth:login`, `auth:logout`, `auth:register`, `auth:magic-link` | Session management. |
| **App** | `app:deploy`, `app:start`, `app:stop`, `app:restart`, `app:destroy`, `app:logs`, `app:run`, `app:env:*` | Full application lifecycle. |
| **System** | `system:status`, `system:info`, `system:check`, `system:ssh` | Host-level inspection and shell access. |
| **Addon** | `addon:create`, `addon:destroy`, `addon:list`, per-addon flows | Backing-service lifecycle. |
| **Backup** | `backup:create`, `backup:list`, `backup:restore`, `backup:delete` | Per [ADR 024](./024-backup-restore-system.md). |
| **Admin** | `admin:create-user`, `admin:reset-password`, `admin:delete-user` | Operator provisioning (server-side entry points per [ADR 014](./014-authentication-bootstrap.md)). |
| **Server** | `server:setup`, `server:update` | Hop3-server lifecycle on the host. |
| **Health** | `healthcheck`, `healthcheck:debug` | Diagnostic commands. |
| **Nix** | `nix:eject` | Template-generated → hand-crafted `hop3.nix` ([ADR 008](./008-nix-builders-2.md)). |

The `hop3` CLI aliases `hop` for brevity. The full command listing is available via `hop3 --help`.

### Commands deliberately excluded or sequenced behind other work

Some commands named in the original kernel are intentionally not part of the core surface, or depend on machinery that other ADRs own:

- **`build` (separate from deploy)**: builds are tied to deploy. A stand-alone `build` command is cheap to add but is not required by operators, so it is not part of the surface.
- **`revert`, `upgrade` / `downgrade`**: these depend on versioned artefacts and the deployment-strategies / artefact-lifecycle machinery owned by [ADR 032](./032-deployment-strategies-artifact-lifecycle.md); they are sequenced behind that work.
- **`new` (project scaffolding)**: operators adopt Hop3 by adding a `hop3.toml` to an existing repo, so scaffolding is low priority.
- **`docker` (run Docker on server)**: out of scope; the server-side SSH shell covers this without a dedicated CLI wrapper.
- **Catalog commands (`search`, `info`, `install`)**: the catalog subsystem is addressed through the web UI first; the CLI surface follows that work rather than leading it.

### Ergonomics and help system

CLI ergonomics (help text, discoverability, error messages) are covered separately in [ADR 036](./036-cli-ergonomics.md).

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

Credentials are stored in `~/.config/hop3-cli/config.toml`, and may also be provided by environment variables (`HOP3_API_TOKEN`, `HOP3_API_URL`). *(Updated 2026-06-23: the original sketch named `~/.hop3/credentials.toml` and illustrative `HOP3_TOKEN`/`HOP3_SERVER_URI` vars; corrected to the implemented location and variables: see [ADR 042](042-cli-context-model.md).)*

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

- CLI architecture overview: [018-cli-architecture.md](018-cli-architecture.md)
