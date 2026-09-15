# Architecture & Design

## Target Users

The primary users of Hop3 are small and medium-sized businesses (SMBs) with limited IT resources. They need IT infrastructure they can deploy and run with minimal complexity. The target user groups are:

### Small and Medium-sized Businesses (SMBs)

**IT Administrators:**

- Want a single portal for managing their IT infrastructure.
- Need to migrate existing services to new hardware or virtual machines with little downtime or complexity.
- Need reliable backup and restore for business continuity.

**Business Owners and Managers:**

- Want to reduce dependency on large upstream vendors and run their IT independently.
- Want to manage their IT infrastructure on a limited budget.

### Managed Service Providers (MSPs)

**Service Providers:**

- Need a flexible, scalable platform for managing many client environments.
- Need a multi-tenant, SaaS-compatible solution they can deploy on-premise for clients or host in a data center.

### Developers and DevOps Teams

**Software Developers:**

- Want to create and deploy applications on a consistent, reliable infrastructure.
- Want an easy-to-use platform for testing and deploying new software modules.

**DevOps Engineers:**

- Need support for DevOps practices such as continuous integration and continuous deployment (CI/CD).
- Want built-in tools for automated testing, monitoring, and scaling of applications.

### Educational Institutions

**IT Departments in Schools and Universities:**

- Need IT infrastructure they can manage at scale for administrative and academic workloads.
- Need secure, reliable ways to manage user accounts, data storage, and application deployment.

### Non-profit Organizations

**IT Volunteers and Staff:**

- Need affordable IT solutions they can run without extensive technical expertise.
- Need secure, manageable infrastructure for data, applications, and communication services.

## Goals and Key Features

Hop3 aims to give these users a platform that is reliable, secure, and efficient. The design goals follow from those needs:

### Solve Sysadmin Daily Problems

- **Easy Software Installation:** Simplify software installation so that it requires little technical expertise.
- **On-premise and Cloud Deployments:** Support both on-premise and cloud deployments, so users can choose their environment.
- **Migrate Software between Machines / Clusters:** Move software and services between machines with minimal downtime.
- **Centralized Management Portal:** Provide one portal as the interface for the whole infrastructure.

### Independence and Control

- **Self-Hosting:** Let users self-host their infrastructure for more control and less reliance on external providers.
- **Software Supply Chain Independence:** Keep the software supply chain independent of third-party dependencies.
- **Simple, Reliable Upgrades:** Keep upgrades simple so they cause minimal disruption and leave existing configurations working.
- **Limit Upstream Dependency:** Reduce reliance on specific upstream projects or vendors.

### Cost Efficiency and Scalability

- **Cost Efficiency:** Run efficiently on low-cost hardware and entry-level virtual private servers.
- **Scalability:** Optimize for single servers and small clusters.

### Security and Resilience

- **Security:** Treat security as a priority across the design: access control, data encryption, secure communications.
- **Secure Software Supply Chain:** Build the software supply chain from trusted sources and verify what comes from them.
- **Data Backup and Restore:** Provide backups that protect data integrity and restore quickly after a failure.
