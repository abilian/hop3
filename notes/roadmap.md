# Roadmap / TODO

## Current Roadmap

Here's the current roadmap for Hop3. Priorities and timelines are subject to change based on community feedback, business priorities and funding.

### P0 (Q2 2024):

Initial goal: just enough to deploy [Abilian SBE](https://github.com/abilian/abilian-sbe-monorepo/).

Features, UX:

- [x] First working version (static sites, python apps, demo apps)

Doc:

- [x] Fix REUSE config
- [x] Basic Documentation / READMEs / etc.

Infra, QA, DX, refactorings:

- [x] Add e2e tests (`make test-e2e`)
- [x] Basic tests and sample apps
- [x] Basic CI (on SourceHut)
- [x] Basic plugin architecture (using, e.g. [pluggy](https://pluggy.readthedocs.io/en/stable/))
- [x] Nix dev env (support for `nix-shell`)
- [x] Test automation (using `nox`)
- [x] Make src/hop3/run/uwsgi.py into a class

### P1 MVP (Q4 2024->Q2 2025):

Features:

- [x] Reorganize code base into sub-projects (monorepo)
- [x] Start multi-OS support (Ubuntu, Archlinux, Fedora, NixOS, Guix, FreeBSD...)
- [ ] Deploy a few more useful apps: Abilian SBE, more...
- [ ] Add postgres, redis, etc. lifecycle support using plugins
- [ ] Improve Python builder (support for poetry, pipenv, uv, etc.)
- [ ] Manage external services (databases, mail, etc.)

Infra, QA, DX, refactorings:

- [x] Unit and integration tests
- [x] Refactor CLI (using `argparse`)]
- [x] Switch to `uv` (from `poetry`)
- [x] Build as a docker image
- [ ] Run as docker image
- [ ] Split class Deployer. Introduce "DeployStep" and "DeployContext" classes.
- [ ] Fix all typing issues (mypy and pyright)
- [ ] Introduce new plugins (where it makes sense)
- [ ] More end-to-end tests, examples
- [ ] e2e CI tests
- [ ] Basic Kubernetes support (via Karmada)

H3NI project:

- [ ] Stabilize and automate Testbed (Hetzner VMs, K8s, Karmada, SMO via PyInfra)
- [ ] Conceptual design for "Application Graph" schema for SMO compatibility
- [ ] Initial Hop3 Plugin development for NEPHELE SMO integration (request transformation, basic communication).
- [ ] Implement functional Hop3 Plugin
- [ ] Implement Basic Predictive Scaling component
- [ ] Demonstrate basic horizontal scaling
- [ ] Document Integration Architecture for Hop3-SMO


### P2 MVP2 (Q3 2025):

Features:

- [ ] Backup / Restore
- [ ] Web App / portal
- [ ] More apps
- [ ] Monitoring
- [ ] (Pluggable) Alternatives to uWSGI, NGINX, ACME, etc.
- [ ] Nix builds
- [ ] Nix runtime
- [ ] Support for (or migration from) Heroku, Render, Docker Compose, Fly… config files,
- [ ] Unified logging
- [ ] CLI
  - [ ] Use an API server (WIP)
  - [ ] Review the UX/DX
  - [ ] Good looking logging (cf. https://bernsteinbear.com/blog/python-parallel-output/)

Infra, QA, DX, refactorings:

- [ ] Reorganize monorepo further
- [ ] Improve plugin architecture, add working events
- [ ] Agents (for distributed deployments)
- [ ] Dedicated infra for e2e tests

H3NI Project:

- [ ] Implement energy-aware placement.
- [ ] Implement advanced adaptive/predictive scaling with actuation.
- [ ] Implement resilience features (e.g., responding to simulated failures).
- [ ] Live migration concepts/PoC.

NGI0 Project:

- [ ] Develop initial Nix package for Hop3 platform components (CLI, server-side agent if applicable)
- [ ] Develop initial Nix builder plugin for applications already in `nixpkgs`
- [ ] Initial design and PoC for Nix-based alternatives to native builders (e.g., Python-specific)
- [ ] Initial build process optimization and benchmarking.
- [ ] Implement/document Security-by-design principles in architecture.


### P3 (Q4 2025):

Features:

- [ ] Unified login (LDAP / IAM)
- [ ] Container / VM support
- [ ] Target other platforms (e.g. SlapOS, NixOS, Guix, etc.)
- [ ] Security (Firewall, WAF, better isolation, etc.)
- [ ] Multi-server support
- [ ] Orchestrator

NGI0 Project:

- [ ] Launch Foundational Website & Blog.
- [ ] Publish Initial Core Documentation (Developer Guide, Admin Manual, End-User Tutorials).
- [ ] Finalize selection and packaging of all 20 F/OSS applications.
- [ ] Finalize Experience Reports for all 20 packaged applications.
- [ ] Finalize and submit/publish Technical Report / Research Paper.
- [ ] Present project findings at relevant conferences/workshops.
- [ ] Start generating Experience Reports for packaged applications.
- [ ] Draft Technical Report / Research Paper on Hop3 & Nix integration / Security.
- [ ] Produce Screencasts & Webinars.
- [ ] Finalize Experience Reports for all 20 packaged applications.
- [ ] Finalize and submit/publish Technical Report / Research Paper.
- [ ] Present project findings at relevant conferences/workshops.


### P4 (Q1 2026):

Features:

- [ ] Hosted version
- [ ] Workload placement
- [ ] Nomad support



## Old TODO
This is an old TODO, kerp for reference only. The "official" TODO is currently in the [README.md](../README.md)

### Features

- [ ] Add postgres, redis, etc. lifecycle support using plugins
- [x] Integrate automated SSL certificate generation and renewal using Let's Encrypt
- [ ] Implement role-based access control (RBAC) for deployed applications
- [ ] Manage external services (databases, mail, etc.)
- [ ] Backup / Restore

### Architecture

- [ ] (Pluggable) Alternatives to uWSGI, NGINX, ACME, etc.
- [ ] Introduce multi-tenant support
- [ ] Agents
- [ ] Multi-server support
- [ ] Target other platforms (e.g. SlapOS, NixOS, Guix, etc.)
- [ ] Container / VM support

### UX for users

- [ ] Web App / portal
- [ ] API server
- [ ] Implement user-friendly web-based management interface
- [ ] Unified login (LDAP / IAM)
- [ ] Continuous improvements based on user feedback and usage metrics

### DX

- [ ] Improve Python builder (support for poetry, pipenv, etc.)
- [ ] Enhance developer experience (DX) by streamlining common tasks and improving tooling
- [ ] Support for (or migration from) Heroku, Render, Docker Compose, Fly… config files
- [ ] Integrate with popular CI/CD pipelines
- [ ] Continuous improvements based on user feedback and usage metrics

### Apps

- [ ] Deploy a few more useful apps: Abilian SBE, more...

### Documentation

- [ ] Create detailed guides for advanced configuration and customization
- [ ] Add troubleshooting section for common deployment issues
- [ ] Develop detailed migration guides for existing users
- [ ] Tutorial for system administrators
- [ ] Tutorial for application developers / packagers

### Infra, QA

- [ ] Improve logging and error reporting mechanisms
- [ ] More end-to-end tests, examples
- [ ] e2e CI tests
- [ ] Optimize deployment scripts for faster performance
- [ ] Develop a more robust plugin architecture

### Code / refactorings

- [ ] Convert to monorepo with suprojects (each with its own dependencies)
- [ ] Fix all typing issues (mypy and pyright)
- [ ] Split class Deployer. Introduce "DeployStep" and "DeployContext" classes.
- [ ] Introduce new plugins (where it makes sense)

### Security

- [ ] SBOMs
- [ ] Security (Firewall, WAF, better isolation, etc.)
- [ ] Implement advanced monitoring and alerting capabilities
- [ ] Conduct regular security audits and integrate automated security scanning
- [ ] Develop comprehensive security documentation and best practices guides
- [ ] Conduct security audits and integrate automated security scanning

### Monitoring and Logging

- [ ] Monitoring
- [ ] Unified logging
- [ ] Implement detailed monitoring and logging for all deployed applications
- [ ] Integrate with popular monitoring and logging tools (e.g., Prometheus, Grafana, ELK stack)
- [ ] Develop automated alerting and notification systems

### Performance

- [ ] Enhance scalability features for high-traffic applications
- [ ] Continuous performance improvements based on user feedback and usage metrics
