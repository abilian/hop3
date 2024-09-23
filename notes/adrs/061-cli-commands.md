# ADR: Basic Commands for the Hop3 Command-Line

Status: Draft

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

The Hop3 CLI will implement a set of commands categorized into Authentication, Marketplace, Development, System-Level Operations, App-Level Operations, and Service Operations. These commands will interact with the server using JSON-RPC over HTTPS.

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

### Marketplace

- `hop3 search`: Search the marketplace for available apps (name + short description).
- `hop3 info`: Get detailed information on a specific app from the marketplace.
- `hop3 install`: Install (or instantiate) an app from the marketplace.

## Action Items

1. Refine the list of commands based on feedback and usability testing.

1. Implement a minimal set of commands for the Hop3 CLI, focusing on essential operations and user needs.

1. Design the whole command-set.

## Related

- CLI commands overview [ADR-060](./060-cli-architecture.md)

## Open Questions

Do we call the command `hop3` or just `hop`?
