# ADR: Using Nix as a Runtime Isolation Mechanism for Applications Hosted by Hop3

## Status

Status: Draft

Version:

- v0.1: Initial draft (2024-07-17)
- v0.2: Tweak following feedback from NLNet (2024-09-23)

## Context and Goals

To enable the security, reliability, and operational efficiency of the Hop3 platform, it is critical to provide robust runtime isolation for the applications it hosts. While traditional containerization tools like Docker offer runtime isolation, they can introduce complexity and security vulnerabilities. Nix, with its purely functional package management system, is traditionally known for its build-time guarantees (reproducibility, determinism). However, Nix also has potential as a runtime tool, particularly in providing isolation between applications and managing services.

The goal of this ADR is to evaluate and leverage Nix’s capabilities to ensure isolation between running applications and to manage applications along with their backing services (such as databases, email servers, certificates, etc.) in a controlled and consistent environment. This aligns with Hop3’s objective of offering a secure, reliable, and user-friendly platform.

## Decision

Hop3 will use Nix not only for build-time management but also for runtime behavior, leveraging its declarative nature to provide isolation between running applications and managing services as resources. This will include managing dependencies, service configuration, and backing services (e.g., databases, email systems, storage) through Nix's package and environment management tools.

## Key Components

### Runtime Isolation with Nix

1. **Isolation Between Running Applications**:

   - **Controlled Environments**: Nix can create isolated environments for each application by ensuring each application has its own, unique set of dependencies and configurations. This can prevent conflicts between applications and ensure they run securely.
   - **Minimal Cross-Application Interference**: Each application will be run in its own isolated environment, making it immune to changes in other applications' environments. This prevents issues such as dependency conflicts or one application affecting the performance of another.

1. **Managing Applications as Services**:

   - **Service Management**: Nix can be used to manage applications as long-running services, leveraging tools like `systemd` to handle service orchestration. Each application deployed in Hop3 can be managed declaratively using Nix, which will handle the starting, stopping, and restarting of services.
   - **Backing Services Management**: Nix can also be extended to manage backing services such as databases, email services, and other resources like SSL certificates. By declaring these services in the Nix configuration, Hop3 can ensure that applications have access to the necessary resources and services, all while being managed in the same reproducible, isolated manner as the applications themselves.

### Implementation Strategy

1. **Nix-Based Runtime Isolation**:

   - **Nix Shells for Isolation**: Use Nix shells or other isolation mechanisms to ensure that each application runs in its own environment with isolated dependencies and runtime configurations. This approach ensures runtime consistency and prevents dependency-related runtime failures.
   - **Declarative Service Management**: Applications and their backing services will be declared in Nix, ensuring that the platform manages not only the deployment but also the runtime lifecycle of both the applications and the resources they depend on.

1. **Managing Backing Services**:

   - **Service Integration**: Use Nix to manage the lifecycle of databases (e.g., PostgreSQL, MySQL), email servers, and other essential services needed by the applications. Nix expressions can be written to declaratively define how these services are installed, started, and linked to the applications.
   - **Certificate and Resource Management**: SSL certificates, storage systems, and other resources required for application operations can also be managed through Nix. By integrating certificate management (e.g., with Let's Encrypt) into the platform's configuration, Hop3 ensures secure, managed communication and availability of essential resources.

### Managing Services with Nix or NixOS

Nix can help manage the lifecycle of backing services in several ways by leveraging its declarative, reproducible nature. How this will be done in practice is still under discussion and will be refined based on feedback and testing.

Here is the current thinking on how Nix can be used to manage services:

#### Declarative Service Configuration (on NixOS)

- **NixOS Modules**: In NixOS (the operating system built around Nix), services such as databases (e.g., PostgreSQL, MySQL) and email servers (e.g., Postfix, Dovecot) can be defined declaratively using NixOS modules. These modules specify how services should be configured, started, and managed. The configuration is entirely reproducible, meaning that rebuilding or restarting the service will always produce the same result.

- **Declarative Resource Management**: Nix allows you to declare not only the application and service dependencies but also the configuration of the services themselves (such as database ports, connection limits, etc.). For example, you can define how PostgreSQL should be set up (e.g., data directory, authentication methods) in the Nix expression, ensuring that the service behaves consistently across deployments.

  Example for PostgreSQL:

  ```nix
  services.postgresql = {
    enable = true;
    dataDir = "/var/lib/postgresql/data";
    authentication = {
      local = [{
        database = "all";
        method = "md5";
      }];
    };
  };
  ```

  This example shows how NixOS can manage the lifecycle of PostgreSQL, ensuring that the database server is started with the correct configuration and that it remains consistent even after reboots or migrations.

#### \*Automatic Service Management (with `systemd`)

- **Systemd Integration**: Nix (on NixOS) integrates seamlessly with `systemd`, the default service manager for Linux, to handle the automatic starting, stopping, and restarting of services. Each service is tied to a systemd unit file that is generated automatically by Nix. This ensures that services like PostgreSQL or an email server are automatically started when needed and are properly managed (restarted in case of failure, stopped on shutdown, etc.).

- **Service Dependencies**: Nix can declaratively manage service dependencies. For example, if an application depends on a PostgreSQL database or an email server, Nix can ensure that those services are started before the application starts. This lifecycle management ensures that services are always available when needed.

  Example:

  ```nix
  systemd.services.myApp = {
    after = [ "postgresql.service" "postfix.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      ExecStart = "/path/to/myApp";
    };
  };
  ```

  This ensures that the application (`myApp`) only starts after PostgreSQL and Postfix services are up and running.

#### Managing Data Migrations and Backups

- **Database Migrations**: Nix can manage migrations by defining version-specific configurations for services like PostgreSQL. Since Nix tracks dependencies and versions precisely, it can ensure that database migrations are applied at the correct time during the upgrade or deployment process. This ensures seamless upgrades of both applications and the databases they depend on.
- **Backups and Restores**: With Nix, the configuration for backup services can be defined declaratively, ensuring consistent and automated backup schedules for databases or other services. Nix can integrate with existing backup tools to provide version-controlled and reliable backup solutions for databases, ensuring that they can be restored in case of data loss.

#### Reproducible Runtime Environments

- **Immutable Infrastructure**: Because Nix configurations are immutable, every deployment of a service like PostgreSQL or an email server will be identical across environments. This ensures that developers can run the same version of PostgreSQL with the same configurations in both development and production, preventing "works on my machine" problems.

- **Version Pinning and Rollbacks**: Nix allows pinning to specific versions of services and easily rolling back to previous versions. This ensures that upgrades to essential services (e.g., from PostgreSQL 13 to 14) can be done safely, with the ability to roll back if something goes wrong.

  Example:

  ```nix
  environment.systemPackages = with pkgs; [
    postgresql_13  # PostgreSQL 13 is explicitly specified.
  ];
  ```

  This guarantees that the specific version of PostgreSQL will always be used unless explicitly changed.

#### SSL Certificates and Other Resources

- **Certificate Management**: Nix can manage SSL certificates for services such as web servers or email servers. Using declarative tools like Let's Encrypt in combination with Nix, you can automatically issue, renew, and install SSL certificates for your services. This ensures that all certificates are managed centrally, making certificate rotation and renewal part of the system’s lifecycle management.

  Example:

  ```nix
  security.acme.certs = {
    mySite = {
      email = "admin@example.com";
      webroot = "/var/www";
      postRun = "systemctl restart nginx";
    };
  };
  ```

  This ensures that SSL certificates are automatically managed and applied to the services without manual intervention.

#### Orchestration of Backing Services

- **Orchestrating Multiple Services**: Nix can orchestrate multiple backing services (databases, caches, email servers, etc.) needed by an application. By specifying the relationship between these services in the Nix configuration, the platform can ensure that all services are deployed and managed correctly as part of the application stack. For example, if an application requires PostgreSQL, Redis, and an email service, Nix can ensure that all these services are deployed together, started in the correct order, and managed declaratively.

### Continuous Improvement

1. **Monitoring and Feedback**:

   - **Performance and Security Monitoring**: Continuous monitoring of the runtime performance and security of isolated environments. Feedback from this monitoring can be used to improve isolation techniques or address security vulnerabilities.
   - **User Feedback**: A feedback loop with users and developers will help improve the runtime isolation and service management mechanisms over time, ensuring they meet real-world use cases.

1. **Community Engagement**:

   - **Nix Community**: Collaborate with the Nix community to adopt best practices and tools for runtime isolation and service management. Leverage existing NixOS tools, `systemd` integrations, and explore emerging runtime isolation practices.
   - **Hop3 Community**: Involve the Hop3 community to gather feedback and contributions on how Nix’s runtime behavior can be optimized for the platform’s specific needs.

## Consequences

### Benefits

- **Runtime Isolation**: Nix provides fine-grained isolation for running applications, ensuring that each application runs in its own environment, independent of other applications. This reduces the risk of dependency conflicts and enhances runtime reliability.
- **Service and Resource Management**: Nix’s declarative configuration model allows not only the applications but also their backing services (e.g., databases, email, certificates) to be managed as part of the same system. This creates a unified approach to managing all aspects of the application environment.
- **Security**: By managing runtime dependencies and services in a controlled environment, Nix minimizes the attack surface and ensures that only the necessary components are included in the runtime.

### Drawbacks

- **Complexity of Runtime Isolation**: While Nix excels at managing build environments, its role in runtime behavior is still evolving. Using Nix for runtime isolation may introduce complexity or unstability that needs to be carefully managed.

## Risks

- **Integration Complexity**: Nix’s role as a runtime isolation tool is still less mature than its build-time capabilities. Ensuring that Nix provides adequate runtime isolation across a wide range of applications and services might be challenging. To mitigate this, Hop3 will leverage `systemd` and other NixOS tools known to manage services effectively.
- **Service Interoperability**: Managing backing services like databases and certificates using Nix could face challenges when integrating with legacy or complex services. Mitigation includes extensive testing and community feedback to ensure compatibility.
- **Runtime Performance**: Using Nix to manage the runtime environment might introduce performance overhead, especially in complex deployments with many services. Continuous performance optimization and monitoring are essential to minimize this impact.

## Action Items

1. **Implement Runtime Isolation**:

   - Use Nix shells or similar mechanisms to isolate the runtime environments of applications and manage their lifecycle declaratively.
   - Ensure that each running application is isolated from others to prevent interference and dependency conflicts.

1. **Service and Resource Management**:

   - Use Nix to manage backing services like databases, email systems, and SSL certificates. Ensure that applications can access these resources in a consistent, secure manner.
   - Automate the deployment and management of certificates (e.g., using Let’s Encrypt) to ensure secure communication between services.

1. **Monitor and Improve**:

   - Implement real-time monitoring of application performance and security within the isolated environments.
   - Continuously optimize Nix expressions and service management strategies based on feedback and monitoring results.

1. **Community Engagement**:

   - Collaborate with the Nix and Hop3 communities to refine and improve the use of Nix as a runtime isolation and service management tool.
   - Provide documentation and support to help users and developers adopt Nix for both build-time and runtime isolation.
