# Hop3 Packages

This directory contains the core packages that make up the Hop3 platform.

## Package Overview

| Package | Entry Point | Description |
|---------|-------------|-------------|
| **hop3-server** | `hop3-server` | Core platform server that orchestrates deployments |
| **hop3-cli** | `hop3` / `hop` | Command-line client for interacting with Hop3 servers |
| **hop3-installer** | `hop3-install` / `hop3-deploy-server` | Installation and deployment toolkit |
| **hop3-tui** | `hop3-tui` | Terminal UI for managing applications |
| **hop3-testing** | `hop3-test` | Test framework and E2E testing utilities |

## hop3-server

The central server that runs on the target deployment machine. Handles:
- JSON-RPC API for CLI/TUI communication
- Application deployment orchestration
- Reverse proxy configuration (Nginx, Caddy, Traefik)
- Database addon management (PostgreSQL, MySQL, Redis)
- Process management via uWSGI

**Stack**: Litestar (ASGI), SQLAlchemy, Pluggy, Dishka

## hop3-cli

Thin client for developers to interact with Hop3 servers. Communicates via JSON-RPC over HTTP or SSH tunneling.

## hop3-installer

Two distinct tools:
- `hop3-install` - Production installer for end users/sysadmins
- `hop3-deploy-server` - Developer tool for deploying/updating Hop3 during development

Uses only Python stdlib for maximum portability.

## hop3-testing

Testing utilities and pytest fixtures for integration and E2E testing. Manages test Docker containers and SSH targets.

## hop3-tui

Experimental keyboard-driven terminal interface built with Textual. Provides dashboard, app management, and log viewing.
