TODO
====

### Features

- [ ] Add postgres, redis, etc. lifecycle support using plugins
- [ ] Integrate automated SSL certificate generation and renewal using Let's Encrypt
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
- [ ] CI on GitHub
- [ ] e2e CI tests
- [ ] Optimize deployment scripts for faster performance
- [ ] Develop a more robust plugin architecture

### Code / refactorings

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
