# Hop3 - Open source platform as a service

<img src="https://abilian.com/static/images/ext/hop3-logo.png"
style="width: 500px; height: auto;" alt="logo hop3"/>
<img
referrerpolicy="no-referrer-when-downgrade"
src="https://stats.abilian.com/matomo.php?idsite=15&amp;rec=1" style="border:0" alt="" />

Build status: [![builds.sr.ht status](https://builds.sr.ht/~sfermigier/hop3.svg)](https://builds.sr.ht/~sfermigier/hop3?)

## About

Hop3 is an open source platform as a service (PaaS): it enable you to deploy and manage your applications seamlessly. It is designed to be simple, secure, and easy to use.

The project is hosted on both [SourceHut](https://git.sr.ht/~sfermigier/hop3) and [GitHub](https://github.com/abilian/hop3).

## TOC

<!-- toc -->

- [Status](#status)
- [Overview](#overview)
- [Goals](#goals)
- [Features (Including Planned Features)](#features-including-planned-features)
- [Technology Stack](#technology-stack)
- [Supported OS](#supported-os)
- [Getting Started](#getting-started)
- [Development and Contribution](#development-and-contribution)
- [Roadmap](#roadmap)
- [Documentation](#documentation)
- [Copyright, Credits and Acknowledgements](#copyright-credits-and-acknowledgements)
- [What's the story behind the name?](#whats-the-story-behind-the-name)
- [Links / References](#links--references)

<!-- tocstop -->

## Status

> [!WARNING]
> This code is still evolving quickly, and not meant for production yet.

Version 0.3.0 (branch `stable`) is the first version that can be used to deploy a few simple web applications. It is not yet feature-complete. It is already used to host some live applications.

Version 0.4.0 (branch `devel`) is the current development version. It is currently undergoing a very large refactoring (spliting the code base into multiple sub-projects, using a plugin architecture, etc.). It is not yet usable.

=> If you want to use Hop3 (or fix bugs on the production branch), please use the `stable` branch.

=> If you want to contribute to Hop3, please use the `devel` branch.

## Overview

Hop3 is an open-source platform designed to enhance cloud computing with a focus on sovereignty, security, sustainability, and inclusivity.

It aims to facilitate access to cloud technologies for a diverse range of users, including small and medium-sized enterprises (SMEs), non-profits, public services, and individual developers. By leveraging robust web, cloud, and open source technologies, Hop3 enables these groups to deploy and manage web applications efficiently and securely.

## Goals

- **Sovereignty**: Empowers users to maintain control over their data and infrastructure, reducing reliance on centralized cloud services.
- **Security and Privacy**: Adopts a secure-by-design approach, integrating advanced security measures and ensuring compliance with privacy regulations like GDPR and the Cyber Resilience Act (CRA).
- **Environmental Sustainability**: Incorporates eco-design principles to reduce the environmental footprint of cloud computing, advocating for sustainable digital practices.
- **Openness and Collaboration**: Developed as an open-source project to encourage community-driven innovation and improvement.
- **Inclusivity and Accessibility**: Ensures the platform is accessible to a diverse audience, including those with different abilities, through comprehensive documentation and support.

## Features (Including Planned Features)

Hop3 provides a comprehensive suite of features (some still in development) designed for robust application management, security, and intelligent automation.

### Management and User Experience

*   **Centralized Web UI:** A powerful web dashboard for managing applications, users, and system settings, complete with real-time analytics and event logs.
*   **User & Access Control:** Integrates with LDAP for centralized authentication and supports Single Sign-On (SSO). A granular Role-Based Access Control (RBAC) system with audit logs allows for precise permission management.
*   **Domain & SSL Management:** Simplifies DNS configuration and automates the entire lifecycle of SSL certificates with services like Let's Encrypt.

### Automation and Orchestration

*   **Intelligent Orchestration Engine:** A built-in engine that manages the deployment, scaling, and resource allocation of applications without requiring external tools like Kubernetes.
*   **Dynamic Scaling & Workload Management:** Automatically scales applications based on demand and intelligently schedules tasks, including offloading heavy computations to more powerful infrastructure.
*   **Automated Lifecycle:** Supports automated deployments through CI/CD integration, automated backups with disaster recovery capabilities, and seamless live migration of running services between nodes without downtime.

### Architecture and Design

*   **Modular and Extensible:** Built on a flexible, pluggable architecture that allows users to add and customize functionality with plugins.
*   **Distributed and Resilient:** Utilizes a distributed, agent-based architecture for decentralized control, ensuring fault tolerance, high availability, and easy scalability.
*   **Comprehensive Security:** Incorporates advanced security measures, including real-time monitoring, encryption for data at rest and in transit, and secure network management tools (firewalls, VPNs, etc.).


## Technology Stack

Hop3's technology stack is carefully chosen to support its goals without relying on conventional containerization tools like Docker or Kubernetes. Instead, it focuses on alternative, lightweight solutions that align with the project's principles of efficiency and sovereignty. The stack includes:

- **Lightweight Isolation**: Utilizes lean isolation technologies privided by POSIX operating systems, and improved by technologies such as Nix or Guix, to ensure efficient resource use and reproducible builds.
- **Decentralized Architecture**: Employs a decentralized model for data storage and processing to enhance sovereignty and resilience.
- **Security Tools**: Incorporates a suite of security tools designed for continuous monitoring, proactive threat mitigation, and compliance with the CRA.
- **Energy-Efficient Computing**: Adopts strategies and technologies aimed at minimizing energy consumption across all operations.
- **Open Standards and Protocols**: Committed to open standards to ensure interoperability and prevent vendor lock-in.

## Supported OS

We *aim* to support a wide range of operating systems, including:

- **Linux**: Ubuntu, Debian, Archlinux, Rocky, Alma, Fedora, NixOS, Guix...
- **BSD**: FreeBSD, OpenBSD, NetBSD.

We run CI tests on the SourceHut platform, which supports a wide range of open source distributions and operating systems. This is a work in progress, and we welcome contributions to fix issues with the current tests or to expand the list of supported OS. See: [.build](.build) for the CI scripts, and https://builds.sr.ht/~sfermigier/ for current build status.

## Getting Started

To begin using Hop3, follow these introductory steps:

1. **Prerequisites**: Familiarize yourself with basic cloud computing concepts and the specific technologies Hop3 employs for virtualization and security.

1. **Installation**:

   - Clone the latest version of Hop3 from the official repository: `git clone https://github.com/abilian/hop3.git`
   - Follow the installation instructions in the `docs/installation.md` to set up Hop3 on your system.

1. **Configuration**: Configuration options can be found in the `config` directory. Adjust these settings to suit your environment and deployment needs.

1. **Documentation**: For detailed information on setup, architecture, and usage, refer to the `docs` folder. This resource includes comprehensive guides and best practices.

## Development and Contribution

Contributions to Hop3 are highly encouraged, whether it involves fixing bugs, adding features, or enhancing documentation. The development and delivery pipeline is designed to be hermetic, reproducible, and highly responsive, integrating modern cross-platform functional package management with continuous integration/continuous delivery (CI/CD). This ensures that the development process is transparent, secure, and efficient.

### Development Environment

To develop Hop3, you will need to set up a Python development environment (tested under various variants of Linux, and MacOS). The project uses Python 3.10+ and some common Python tools for environment and dependency management. We assume you are already familiar with these prerequisites.

- **Poetry**: You must have Poetry installed. We are in the process of phasing out Poerty in favor of uv, but for now, you need to have Poetry installed.
- **uv**: You need uv installed. Run `brew install uv` or run the installer.
- **nox**: You need nox installed. Run `uv tool install nox`.
- **Just**: You need Just installed. Run `brew install just` or `cargo install just`.

You can check your environment by running `python3 scripts/check-dev-env.py` or `make check-dev-env`, assuming you have `make` installed.

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

- [Getting Started](./docs/dev/getting-started.md)
- [Core Values](./docs/dev/core-values.md)
- [Contributing](./docs/dev/contributing.md)
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

The current roadmap for Hop3 is available [here](notes/roadmap.md).

## Documentation

See the [docs](./docs) directory for detailed information on Hop3's architecture, installation, and usage.

Deployed at [https://hop3.cloud](https://hop3.cloud).

## Copyright, Credits and Acknowledgements

### Authors

Hop3 contains code from Piku, which shares some of the goals of Hop3 / Nua but also has some significant differences in goals and principles, as well as in architecture (Hop3 is modular and pugin-based, Piku is a single-file script).

Hop3 also contains code from Nua, written by the Abilian development team, and contributors. The two projects share most goals and principles, except Nua is based on containers and Hop3 is not. The two projects may ultimately merge in the future (or not).

Other inspirations include:

- [Dokku](https://dokku.com/)
- [fig aka docker-compose](https://pypi.org/project/docker-compose/)

The following people have contributed to Hop3:

- [Stefane Fermigier](https://fermigier.com/) has created and maintains Nua and Hop3.

- [Jérôme Dumonteil](<>) has contributed to and maintans Nua.

- [Rui Carmo](https://github.com/rcarmo) (and other Piku contributors) for the original Piku.

- [Abilian](https://www.abilian.com/) is the company behind Nua and Hop3.

### Licensing / REUSE Compliance

<img src="./docs/img/reuse-horizontal.png" alt="REUSE logo"/>

Hop3 is licensed under the AGPL-3.0 License, except for vendored code.
See the [LICENSE](LICENSE) file for more information.

Here are the REUSE compliance results for Hop3 (as of 2024/07/25):

> - Bad licenses: 0
> - Deprecated licenses: 0
> - Licenses without file extension: 0
> - Missing licenses: 0
> - Unused licenses: 0
> - Used licenses: CC0-1.0, BSD-3-Clause, AGPL-3.0-only, CC-BY-4.0, MIT
> - Read errors: 0
> - Files with copyright information: 310 / 310
> - Files with license information: 310 / 310
>
> Congratulations! Your project is compliant with version 3.2 of the REUSE Specification :-)

### Funding

This project is partly funded through the [NGI0 Commons Fund](https://nlnet.nl/commonsfund), a fund established by [NLnet](https://nlnet.nl) with financial support from the European Commission's [Next Generation Internet](https://ngi.eu) programme, under the aegis of [DG Communications Networks, Content and Technology](https://commission.europa.eu/about-european-commission/departments-and-executive-agencies/communications-networks-content-and-technology_en) under grant agreement No [101135429](https://cordis.europa.eu/project/id/101135429). Additional funding is made available by the [Swiss State Secretariat for Education, Research and Innovation](https://www.sbfi.admin.ch/sbfi/en/home.html) (SERI).

More information here: <https://nlnet.nl/project/Hop3-Nixified/>

## What's the story behind the name?

"Hop3" (or more precisely "Hop^3" or "Hop cubed") is a pun on "Hop, hop, hop!" which is a French expression used to encourage quick action or to hurry someone up. It's akin to saying "Let's go!" or "Hurry up!" in English. It can also convey a sense of enthusiasm or encouragement to get moving or to proceed with something. It generally carries a light, motivating tone.

## Links / References

- [Hop3 on PyPI](https://pypi.org/project/hop3/)
- [Hop3 on GitHub](https://github.com/abilian/hop3)
- [Hop3 on SourceHut](https://git.sr.ht/~sfermigier/hop3) (mirror)
- [Live Discussion](https://matrix.to/#/#hop3:matrix.org)
- [Nua](https://nua.rocks/) (Hop3's predecessor)
- [Piku](https://piku.github.io/) (Hop3's inspiration)
- [Sailor](https://github.com/mardix/sailor) (Another fork of Piku)
- [Abilian](https://www.abilian.com/) (Hop3's sponsor -> buy support from us)
- [Abilian SBE](https://github.com/abilian/abilian-sbe-monorepo/) (One of the applications that can be deployed with Hop3 - Soon)
