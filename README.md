# Hop3 - Deploy and manage web applications on a single server

<img src="https://abilian.com/static/images/ext/hop3-logo.png"
style="width: 500px; height: auto;" alt="logo hop3"/>
<img
referrerpolicy="no-referrer-when-downgrade"
src="https://stats.abilian.com/matomo.php?idsite=15&amp;rec=1" style="border:0" alt="" />

Build status: [![builds.sr.ht status](https://builds.sr.ht/~sfermigier/hop3.svg)](https://builds.sr.ht/~sfermigier/hop3?)

## About

Hop3 is a tool to deploy and manage web applications on a single server (currently). It is designed to be simple,
secure, and easy to use.

The project is hosted on both [SourceHut](https://git.sr.ht/~sfermigier/hop3)
and [GitHub](https://github.com/abilian/hop3).

> [!WARNING]
> This code is still evolving quickly, and not meant for production yet.

## Overview

Hop3 is an open-source platform designed to enhance cloud computing with a focus on sovereignty, security, sustainability, and inclusivity.

It aims to facilitate access to cloud technologies for a diverse range of users, including small and medium-sized enterprises (SMEs), non-profits, public services, and individual developers. By leveraging robust web, cloud, and open source technologies, Hop3 enables these groups to deploy and manage web applications efficiently and securely.

### Goals

- **Sovereignty**: Empowers users to maintain control over their data and infrastructure, reducing reliance on centralized cloud services.
- **Security and Privacy**: Adopts a secure-by-design approach, integrating advanced security measures and ensuring compliance with privacy regulations like GDPR.
- **Environmental Sustainability**: Incorporates eco-design principles to reduce the environmental footprint of cloud computing, advocating for sustainable digital practices.
- **Openness and Collaboration**: Developed as an open-source project to encourage community-driven innovation and improvement.
- **Inclusivity and Accessibility**: Ensures the platform is accessible to a diverse audience, including those with different abilities, through comprehensive documentation and support.

## Features

(Some of these features are still in development.)

### Web-Based Management Interface

- **Centralized Management**: Hop3 offers a robust web-based interface for managing applications, users, and system settings. This intuitive dashboard provides comprehensive monitoring and control of the server.

### User Management and Single Sign-On (SSO)

- **Integrated LDAP**: Hop3 integrates with LDAP for centralized user management and authentication.
- **SSO**: Provides Single Sign-On capabilities across all applications, enabling users to access multiple services with a single login.

### Role-Based Access Control (RBAC)

- **Granular Permissions**: Implements RBAC to manage permissions for different users and groups, allowing administrators to control access to various functionalities and applications.

### Automated Backups and Restore

- **Data Protection**: Offers automated backup and restore functionalities to protect against data loss. Includes scheduling regular backups and providing easy restoration processes.

### Domain Management and SSL Certificates

- **DNS Configuration**: Provides tools for managing domain names, including DNS configuration.
- **SSL Management**: Integrates automated SSL certificate management using services like Let's Encrypt to ensure secure communication.

### Modular Design

- **Pluggable Modules**: Features a modular architecture where functionalities are provided by different modules. Administrators can install, configure, and manage these modules independently, allowing for flexible and scalable deployments.

### Comprehensive Network Management

- **Network Services**: Integrates robust network management features such as firewall, VPN, DHCP, DNS, and proxy services, ensuring that Hop3 can handle complex network configurations and provide secure access to applications.

### Security and Resilience Enhancements

- **Advanced Security Measures**: Incorporates advanced security tools for continuous monitoring and proactive threat mitigation.
- **Redundancy and Failover**: Implements redundancy and failover mechanisms to ensure continuous availability.
- **Monitoring and Alerts**: Sets up real-time monitoring and alerting systems to detect and respond to issues promptly.

### Distributed, Agent-Based Architecture

- **Decentralized Control**: Employs a decentralized model for data storage and processing to enhance sovereignty and resilience, using principles from the theory of promises for coordination between agents.
- **Scalability and Fault Tolerance**: Adopts a distributed, agent-based architecture to enhance scalability and fault tolerance, allowing for the seamless addition of nodes and self-healing capabilities.

### Technology Stack

Hop3's technology stack is carefully chosen to support its goals without relying on conventional containerization tools like Docker or Kubernetes. Instead, it focuses on alternative, lightweight solutions that align with the project's principles of efficiency and sovereignty. The stack includes:

- **Lightweight Isolation**: Utilizes lean isolation technologies privided by POSIX operating systems, and improved by technologies such as Nix or Guix, to ensure efficient resource use and reproducible builds.
- **Decentralized Architecture**: Employs a decentralized model for data storage and processing to enhance sovereignty and resilience.
- **Security Tools**: Incorporates a suite of security tools designed for continuous monitoring and proactive threat mitigation.
- **Energy-Efficient Computing**: Adopts strategies and technologies aimed at minimizing energy consumption across all operations.
- **Open Standards and Protocols**: Committed to open standards to ensure interoperability and prevent vendor lock-in.


## Getting Started

To begin using Hop3, follow these introductory steps:

1. **Prerequisites**: Familiarize yourself with basic cloud computing concepts and the specific technologies Hop3
   employs for virtualization and security.

2. **Installation**:
    - Clone the latest version of Hop3 from the official repository: `git clone https://github.com/abilian/hop3.git`
    - Follow the installation instructions in the `docs/installation.md` to set up Hop3 on your system.

3. **Configuration**: Configuration options can be found in the `config` directory. Adjust these settings to suit your
   environment and deployment needs.

4. **Documentation**: For detailed information on setup, architecture, and usage, refer to the `docs` folder. This
   resource includes comprehensive guides and best practices.


## Development and Contribution

Contributions to Hop3 are highly encouraged, whether it involves fixing bugs, adding features, or enhancing documentation. The development and delivery pipeline is designed to be hermetic, reproducible, and highly responsive, integrating modern cross-platform functional package management with continuous integration/continuous delivery (CI/CD). This ensures that the development process is transparent, secure, and efficient.

### Development Environment

To develop Hop3, you will need to set up a Python development environment (tested under various variants of Linux, and MacOS). The project uses Python 3.10+ and Poetry for environment and dependency management. We assume you are already familiar with these prerequisites.

- **NixOS/Nix**: If using NixOS or Nix, you can use the provided `shell.nix` file to set up a development environment.
- **Test Automation**: We use `nox` for test automation. You can run `nox` to execute all tests, or `nox -l` to list available sessions.
- **Development Tools**: We use `abilian-devtools` for various development tasks. This includes `make` targets for common tasks, such as running tests, formatting code, and checking for typing issues. Run `make help` to see a list of the main available targets.

### Development and Delivery Pipeline

To ensure a hermetic, reproducible, and highly responsive internal delivery process, Hop3 integrates modern cross-platform functional package management with CI/CD. This approach leverages Nix to make the entire dependency tree transparent and validatable, enhancing the reliability and security of the delivery pipeline.

#### CI/CD Integration

- **Continuous Integration**: Implement CI pipelines to automatically build and test code changes, ensuring that all code is continuously validated and ready for deployment.
- **Continuous Delivery**: Automate the deployment process to ensure that new features and updates can be delivered quickly and reliably to production.

#### Package Management

- **Nix Package Management**: Use Nix for package management to achieve deterministic builds, minimize dependency conflicts, and ensure reproducibility. Nix provides a consistent environment for building and deploying applications, making it suitable for even the most critical environments.

#### Compliance and Transparency

- **Software Bill of Materials (SBOM)**: Automatically generate compliance-ready CycloneDX Software Bill of Materials using tools like Genealogos. This ensures that all dependencies are transparent and verifiable, aiding in compliance and security audits.

### Contributing

Please refer to the following key documents for contribution guidelines:

- [Contributing](./docs/dev/contributing.md)
- [Core Values](./docs/dev/core-values.md)
- [Governance](./docs/dev/governance.md)
- [Code of Conduct](./docs/policies/code-of-conduct.md)
- [Licenses](./LICENSES)

### Community Engagement

Engage with the Hop3 community:

- **GitHub Issues**: For bug reports and feature suggestions.
- **Matrix Chat**: Join the live discussion on Matrix at [#hop3:matrix.org](https://matrix.to/#/#hop3:matrix.org).

The following tools will soon be available:

- **Community Forums/Discussion Boards**: For discussions, questions, and community support.
- **Mailing List**: Subscribe to receive updates, announcements, and participate in discussions.

<!-- For additional information, visit the official Hop3 project page or reach out to the team via our support channels. -->

### Additional Notes

- **Documentation**: For detailed information on setup, architecture, and usage, refer to the `docs` folder. This resource includes comprehensive guides and best practices.
- **Continuous Improvement**: We welcome feedback and contributions from the community to continuously improve Hop3. Your participation is key to the success of this open-source project.


## Roadmap

Here's the current roadmap for Hop3. Priorities and timelines are subject to change based on community feedback, business priorities and funding.

See also the informal [TODO](./notes/todo.md) list.

### P0 (MVP, Q2 2024):

Initial goal: just enough to deploy [Abilian SBE](https://github.com/abilian/abilian-sbe-monorepo/).

Features, UX:

- [x] First working version (static sites, python apps, demo apps)
- [ ] Deploy a few more useful apps: Abilian SBE, more...
- [ ] Add postgres, redis, etc. lifecycle support using plugins

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
- [X] Make src/hop3/run/uwsgi.py into a class
- [ ] Split class Deployer. Introduce "DeployStep" and "DeployContext" classes.
- [ ] Fix all typing issues (mypy and pyright)

### P1 (Q3 2024):

Features:

- [ ] More apps
- [ ] Review / improve CLI DX
  - [ ] Use an API server
  - [ ] Good looking logging (cf. https://bernsteinbear.com/blog/python-parallel-output/)
- [ ] Improve Python builder (support for poetry, pipenv, etc.)
- [ ] Manage external services (databases, mail, etc.)
- [ ] Backup / Restore
- [ ] Web App / portal
- [ ] API server

Infra, refactorings:

- [ ] Introduce new plugins (where it makes sense)
- [ ] More end-to-end tests, examples
- [ ] CI on GitHub
- [ ] e2e CI tests

### P2 (Q4 2024):

- [ ] More apps
- [ ] Agents
- [ ] Target other platforms (e.g. SlapOS, NixOS, Guix, etc.)
- [ ] Security (Firewall, WAF, better isolation, etc.)
- [ ] Monitoring
- [ ] (Pluggable) Alternatives to uWSGI, NGINX, ACME, etc.
- [ ] Support for (or migration from) Heroku, Render, Docker Compose, Fly… config files,

### P3 (S1 2025):

- [ ] More apps
- [ ] Multi-server support
- [ ] Unified logging
- [ ] Unified login (LDAP / IAM)
- [ ] Container / VM support

## Documentation

See the [docs](./docs) directory for detailed information on Hop3's architecture, installation, and usage.

Will soon be deployed at [https://doc.hop3.cloud](https://doc.hop3.cloud).

## Copyright, Credits and Acknowledgements

### Authors

Hop3 contains code from Piku, which shares some of the goals of Hop3 / Nua but also has some significant differences in
goals and principles, as well as in architecture (Hop3 is modular and pugin-based, Piku is a single-file script).

Hop3 also contains code from Nua, written by the Abilian development team, and contributors. The two projects share most
goals and principles, except Nua is based on containers and Hop3 is not. The two projects may ultimately merge in the
future (or not).

Other inspirations include:

- [Dokku](https://dokku.com/)
- [fig aka docker-compose](https://pypi.org/project/docker-compose/)

The following people have contributed to Hop3:

- [Stefane Fermigier](https://fermigier.com/) has created and maintains Nua and Hop3.
- [Jérôme Dumonteil]() has contributed to and maintans Nua.
- [Rui Carmo](https://github.com/rcarmo) (and other Piku contributors) for the original Piku.

- [Abilian](https://www.abilian.com/) is the company behind Nua and Hop3.

### Licensing / REUSE Compliance

<img src="./docs/img/reuse-horizontal.png" alt="REUSE logo"/>

Hop3 is licensed under the AGPL-3.0 License, except for vendored code.
See the [LICENSE](LICENSE) file for more information.

> * Bad licenses: 0
> * Deprecated licenses: 0
> * Licenses without file extension: 0
> * Missing licenses: 0
> * Unused licenses: 0
> * Used licenses: AGPL-3.0-only, CC0-1.0, MIT, CC-BY-4.0
> * Read errors: 0
> * files with copyright information: 125 / 125
> * files with license information: 125 / 125
>
> Congratulations! Your project is compliant with version 3.0 of the REUSE Specification :-)

## What's the story behind the name?

"Hop3" (or more precisely "Hop^3" or "Hop cubed") is a pun on "Hop, hop, hop!" which is a French expression used to
encourage quick action or to hurry someone up. It's akin to saying "Let's go!" or "Hurry up!" in English. It can also
convey a sense of enthusiasm or encouragement to get moving or to proceed with something. It generally carries a light,
motivating tone.

## Links / References

- [Hop3 on PyPI](https://pypi.org/project/hop3/)
- [Hop3 on GitHub](https://github.com/abilian/hop3)
- [Hop3 on SourceHut](https://git.sr.ht/~sfermigier/hop3) (mirror)
- [Live Discussion](https://matrix.to/#/#hop3:matrix.org)
- [Nua](https://nua.rocks/) (Hop3's predecessor)
- [Piku](https://piku.github.io/) (Hop3's inspiration)
- [Sailor](https://github.com/mardix/sailor) (Another fork of Piku)
- [Abilian](https://www.abilian.com/) (Hop3's sponsor / buy support from us)
- [Abilian SBE](https://github.com/abilian/abilian-sbe-monorepo/) (One of the applications that can be deployed with Hop3 - Soon)
