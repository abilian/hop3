# Hop3 - Deploy and manage web applications on a single server

## About

Hop3 is a tool to deploy and manage web applications on a single server (currently). It is designed to be simple, secure, and easy to use.

## Overview

Hop3 is an open-source platform aimed at enhancing cloud computing with a focus on sovereignty, security, sustainability, and inclusivity. 

It is designed to facilitate access to cloud technologies for a wide range of users, including small and medium-sized enterprises (SMEs), non-profits, public services, and individual developers. By leveraging existing, robust web, cloud and open source technologies, Hop3 enables these groups to deploy and manage web applications efficiently and securely.

## Key Features

- **Sovereignty**: Empowers users to maintain control over their data and infrastructure, aiming to reduce reliance on centralized cloud services.
- **Security and Privacy**: Adopts a secure-by-design approach, integrating advanced security measures and ensuring compliance with privacy regulations like GDPR.
- **Environmental Sustainability**: Incorporates eco-design principles to reduce the environmental footprint of cloud computing, advocating for sustainable digital practices.
- **Openness and Collaboration**: Developed as an open-source project to encourage community-driven innovation and improvement.
- **Inclusivity and Accessibility**: Ensures the platform is accessible to a diverse audience, including those with different abilities, through comprehensive documentation and support.

## Technology Stack

Hop3's technology stack is carefully chosen to support its goals without relying on conventional containerization tools like Docker or Kubernetes. Instead, it focuses on alternative, lightweight solutions that align with the project's principles of efficiency and sovereignty. The stack includes:

- **Lightweight Isolation**: Utilizes lean isolation technologies to ensure efficient resource use.
- **Decentralized Architecture**: Employs a decentralized model for data storage and processing to enhance sovereignty and resilience.
- **Security Tools**: Incorporates a suite of security tools designed for continuous monitoring and proactive threat mitigation.
- **Energy-Efficient Computing**: Adopts strategies and technologies aimed at minimizing energy consumption across all operations.
- **Open Standards and Protocols**: Committed to open standards to ensure interoperability and prevent vendor lock-in.

## Getting Started

To begin using Hop3, follow these introductory steps:

1. **Prerequisites**: Familiarize yourself with basic cloud computing concepts and the specific technologies Hop3 employs for virtualization and security.

2. **Installation**:
   - Download the latest version of Hop3 from the official repository: `git clone https://github.com/hop3-project/hop3.git`
   - Follow the installation instructions in the `docs/installation.md` to set up Hop3 on your system.

3. **Configuration**: Configuration options can be found in the `config` directory. Adjust these settings to suit your environment and deployment needs.

4. **Documentation**: For detailed information on setup, architecture, and usage, refer to the `docs` folder. This resource includes comprehensive guides and best practices.

## Contributing

Contributions to Hop3 are highly encouraged, whether it involves fixing bugs, adding features, or enhancing documentation. Please refer to the `CONTRIBUTING.md` file for contribution guidelines.

## License

Hop3 is licensed under the Apache License, Version 2.0. See the `LICENSE` file for more details.

## Support and Community

Engage with the Hop3 community:
- **GitHub Issues**: For bug reports and feature suggestions.
- **Community Forums/Discussion Boards**: For discussions, questions, and community support.
- **Mailing List**: Subscribe to receive updates, announcements, and participate in discussions.

For additional information, visit the official Hop3 project page or reach out to the team via our support channels.

## Roadmap

### P0 (MVP):

Goal: just enough to deploy [Abilian SBE](https://github.com/abilian/abilian-sbe-monorepo/).

- [x] Split large module
- [x] Add e2e tests
- [x] Modernize code (drop support for python < 3.10)
- [x] Basic plugin architecture (using, e.g. [pluggy](https://pluggy.readthedocs.io/en/stable/))
- [ ] Add postgres, redis, etc. support using plugins
- [ ] Working version
- [ ] Finish code cleanup (renaming, splitting large functions / modules, etc.)
- [ ] Rewrite documentation / READMEs / etc.

### P1:

- [ ] Refactor code using classes (where it makes sense)
- [ ] Review / improve CLI DX
- [ ] Improve Python builder (support for poetry, pipenv, etc.)
- [ ] Manage external services (databases, etc.)
- [ ] More end-to-end tests, examples
- [ ] CI/CD
- [ ] Web App

### P2:

- [ ] Target other platforms (e.g. SlapOS, NixOS, docker, etc.)
- [ ] Security (Firewall, WAF, better isolation, etc.)
- [ ] Monitoring
- [ ] Backup / Restore
- [ ] (Pluggable) Alternatives to uWSGI, NGINX, etc.

### P3: 

- [ ] Multi-server support
- [ ] Unified logging
- [ ] Unified login
- [ ] Container / VM support

## Status

**Not working yet.**

## Documentation

TODO.

## Credits

Hop3 contains some code from Piku, which shares some of the Hop3 / Nua goals but also has some significant differences in goals and principles.

Hop3 also contains code from Nua, written by the Abilian development team, and contributors.

Other inspirations include:

- [Dokku]()
- [Flynn]()
- [fig aka docker-compose]()

The following people have contributed to Hop3:

- [Stefane Fermigier](https://fermigier.com/) has created Nua and Hop3.
- [Jérôme Dumonteil]() has contributed to Nua and Hop3.
- [Rui Carmo](https://github.com/rcarmo) (and other Piku contributors) for the original Piku.

- [Abilian](https://www.abilian.com/) is the company behind Nua and Hop3.

## What's the story behind the name?

"Hop3" (or more precisely "Hop^3" or "Hop cubed") is a pun on "Hop, hop, hop!" which is a French expression used to encourage quick action or to hurry someone up. It's akin to saying "Let's go!" or "Hurry up!" in English. It can also convey a sense of enthusiasm or encouragement to get moving or to proceed with something. It generally carries a light, motivating tone.
