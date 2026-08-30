# Developer Documentation

This documentation is intended for developers who want to contribute to Hop3.

## Quick Start

- [Getting Started](getting-started.md) - Set up your development environment
- [Contributing](contributing.md) - How to contribute to the project
- [Testing Cheat Sheet](testing-cheat-sheet.md) - Quick reference for running tests

## Architecture

- [Architecture Overview](architecture.md) - System design and components
- [Orchestration](orchestration.md) - How deployment orchestration works
- [Protocol Reference](protocol-reference.md) - JSON-RPC API specification

## Testing

- [Testing Guide](testing.md) - Comprehensive testing documentation
- [Testing Cheat Sheet](testing-cheat-sheet.md) - Quick command reference
- [Testing Strategy](testing-strategy.md) - Test layers and philosophy
- [DI Testing Guide](di-testing-guide.md) - Dependency injection in tests
- [Installer Testing](installer-testing.md) - Testing the installer

## Catalog

- [Catalog Lifecycle](catalog-lifecycle.md) - Statuses, the two runners, publish → verify → promote
- [Publishing a Catalog](catalog-publishing.md) - Signing keys, serials, staging, key rotation
- [Staging a Catalog](catalog-staging.md) - Sideloading a signed catalog onto your own box

## Plugins

- [Plugin Development](plugin-development.md) - How to create plugins
- [Hook Specifications](hook-specifications.md) - Available plugin hooks
- [External Plugins](external-plugins.md) - Third-party plugin support
- [Example Plugins](examples/plugins/README.md) - Sample plugin implementations

## Packages

- [Package Overview](packages/index.md) - Monorepo structure
- [hop3-server](packages/hop3-server.md) - Core server package
- [hop3-cli](packages/hop3-cli.md) - Command-line client
- [hop3-installer](packages/hop3-installer.md) - Installation tools
- [hop3-tui](packages/hop3-tui.md) - Terminal UI
- [hop3-testing](packages/hop3-testing.md) - Test framework

## Operations

- [Branching Strategy](branching-strategy.md) - Git workflow
- [DNS Configuration](dns-configuration.md) - DNS setup for development

## Project

- [Core Values](core-values.md) - Project principles
- [Governance](governance.md) - Decision making process
