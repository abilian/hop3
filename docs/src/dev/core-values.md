# Hop3 Core Values and Design Principles

Hop3 is an open-source project designed to simplify the deployment and management of web applications and services across a variety of environments, from low-end devices to cloud and edge computing platforms. At its core, Hop3 embodies principles of efficiency, inclusivity, and simplicity, aiming to make advanced technology accessible to a broad audience, including individual developers, hobbyists, educational institutions, and small to medium enterprises.

With a focus on leveraging standard tooling and minimizing dependencies, Hop3 adheres to the 12-factor app methodology to ensure applications are portable, scalable, and maintainable. The project is built on a foundation of readable and functional code, emphasizing user-centric design to cover a wide range of use cases with sensible defaults and flexible configuration options.

Hop3's architecture is designed to be open and extensible, encouraging community contributions and the development of plugins to extend its core functionality. By prioritizing modern security practices, backward compatibility, and support for major Linux distributions, Hop3 aims to provide a reliable and future-proof platform that promotes sustainable digital practices and fosters an inclusive open-source community.

## Core Principles and Values

1. **Efficiency Across Environments:** Optimized for performance not only on low-end devices but also in cloud (small to large VM, bare metal) and edge computing environments, ensuring broad accessibility and adaptability.
1. **Inclusivity in Technology:** Designed to be accessible to individual developers, hobbyists, K-12 schools, and small to medium enterprises, promoting digital literacy and innovation across diverse communities.
1. **Simplicity in Code:** Strives for a maintainable codebase through a modular and plugin-oriented architecture, ensuring that each component is easy to understand and maintain. This approach allows developers to focus on specific areas of the platform without being overwhelmed by its entirety, promoting clarity and efficiency in development.
1. **Minimal Dependencies:** Maintains a lean architecture with minimal external dependencies to ensure reliability, ease of installation, straightforward updates, and software supply chain independence.
1. **Adherence to 12-Factor App Methodology:** Embraces the principles of the 12-factor app to promote portability, scalability, and a seamless development-to-deployment workflow.
1. **User-Centric Design:** Focuses on simplifying the user experience, from setup to deployment, ensuring that common use cases are intuitive and well-supported.
1. **Broad Use Case Coverage:** Aims to address a wide range of deployment scenarios, covering the most common needs with sensible defaults and flexible configuration options.
1. **Integration with Standard Ecosystems:** Leverages widely-used tools and platforms (e.g., Git, SSH) and supports major Linux distributions, ensuring compatibility and ease of use across different environments.
1. **Modern and Secure Defaults:** Provides sensible, secure defaults for all features, with a focus on modern security practices, compliance standards, and software supply chain security.
1. **Open and Extensible:** Encourages community contributions and extensions through a plugin architecture, allowing for the integration of additional services and tools as needed.
1. **Backward Compatibility and Future-Proofing:** Balances innovation with the preservation of backward compatibility, ensuring long-term viability and support for legacy systems where feasible.
1. **Sustainability and Openness:** Promotes sustainable digital practices and open-source collaboration, contributing to a resilient and inclusive future for the internet.

## Hop3 and the 12-Factor App Methodology

The 12-factor app methodology is a set of practices for building modern web applications to ensure they are portable, scalable, and maintainable in a Platform-as-a-Service (PaaS) environment. Hop3 aligns with these principles to provide a robust and efficient platform for deploying web applications, promoting best practices in development and operations.

1. **Codebase:** One codebase tracked in version control with many deploys. Hop3 encourages a single codebase for each application, version-controlled with Git, allowing for multiple deployments across different environments.
1. **Dependencies:** Explicitly declare and isolate dependencies. Hop3 supports virtual environments, ensuring all dependencies are explicitly declared and isolated.
1. **Config:** Store configuration in the environment. Hop3 allows environment variables to be defined in a separate `ENV` file or through the platform's configuration tools, keeping sensitive and environment-specific configurations out of the code.
1. **Backing Services:** Treat backing services as attached resources. Hop3's plugin architecture can support the integration of external services (like databases, messaging systems, etc.) as attached resources, allowing for easy swap and reconfiguration without code changes.
1. **Build, Release, Run:** Strictly separate build and run stages. Hop3 can automate the build process with CI/CD pipelines, creating immutable releases that are then deployed, ensuring a clear separation between build, release, and run stages.
1. **Processes:** Execute the app as one or more stateless processes. Hop3 encourages stateless application design, where any required state is stored in a backing service, ensuring scalability and resilience.
1. **Port Binding:** Export services via port binding. Applications deployed with Hop3 can bind to a given port provided by the environment for HTTP services, adhering to the principle of self-contained services.
1. **Concurrency:** Scale out via the process model. Hop3's underlying technologies (like uWSGI for Python applications) support process-based scaling, allowing applications to handle multiple concurrent requests efficiently.
1. **Disposability:** Maximize robustness with fast startup and graceful shutdown. Hop3 supports and encourages applications that can be quickly started and gracefully shut down, making them robust and minimizing downtime during scaling and deployment.
1. **Dev/Prod Parity:** Keep development, staging, and production as similar as possible. Hop3's deployment methodology and support for environment variables make it easier to maintain parity across different environments, reducing "works on my machine" issues.
1. **Logs:** Treat logs as event streams. Hop3 can be configured to treat logs as event streams, pushing them to a centralized logging service for analysis without requiring changes to the application code.
1. **Admin Processes:** Run admin/management tasks as one-off processes. Hop3 can execute administrative or maintenance tasks as one-off processes, either through direct command execution or through the platform's task scheduling mechanisms.

More details online: [The 12 Factor App @ Abilian Lab](https://lab.abilian.com/Tech/Cloud/The%2012%20Factor%20App/)

## Hop3's Vision for Security

Hop3 is committed to providing a secure platform for deploying and managing web applications. Drawing from best practices in cybersecurity, our security model emphasizes resilience, transparency, user empowerment, and proactive defense. By adopting a "trust nothing" approach, minimizing the attack surface, and leveraging the power of open source, Hop3 aims to provide a secure, reliable, and user-friendly platform for deploying and managing web applications. Our commitment to continuous monitoring, user education, and compliance ensures that Hop3 remains a trusted choice for developers, companies, small and large, governmental and educational institutions, and open source hobbyist alike.

Below are the key principles guiding Hop3’s approach to security:

1. **Trust Nothing Approach**:

   - **Principle**: Assume that every component and interaction could be compromised.
   - **Implementation**: Use end-to-end encryption, rigorous access controls, and frequent security audits to minimize trust dependencies. Employ multi-factor authentication (MFA) and role-based access controls (RBAC) to ensure only authorized users have access to sensitive data and operations.

1. **Minimization of Attack Surface**:

   - **Principle**: Reduce the potential points of entry for attackers.
   - **Implementation**: Keep the architecture lean by minimizing dependencies and avoiding unnecessary components. Regularly update and patch all software components to mitigate known vulnerabilities. Use containerization to isolate applications and services, thereby limiting the impact of any single breach.

1. **Data Security**:

   - **Principle**: Protect data at rest and in transit.
   - **Implementation**: Encrypt all data stored in databases, filesystems, and backups. Use TLS/SSL to encrypt data transmitted over networks. Implement stringent data retention policies to minimize the amount of sensitive data stored and ensure timely deletion of unnecessary data.

1. **Continuous Monitoring and Incident Response**:

   - **Principle**: Detect and respond to threats in real-time.
   - **Implementation**: Integrate centralized logging and monitoring systems to collect and analyze security events. Use intrusion detection systems (IDS) and automated threat detection tools to identify potential security incidents. Establish clear incident response protocols to address and mitigate breaches swiftly.

1. **Open Source Transparency**:

   - **Principle**: Leverage the transparency of open source to enhance security.
   - **Implementation**: Use open-source software where possible to allow for community scrutiny and auditing. Encourage contributions from the community to identify and fix security issues. Regularly conduct and participate in security audits and code reviews to ensure the integrity of the codebase.

1. **Isolation and Containment**:

   - **Principle**: Isolate critical components to prevent lateral movement of attackers.
   - **Implementation**: Use network segmentation and firewalls to isolate critical components of the infrastructure. Deploy applications in isolated containers or virtual machines to prevent an attacker from moving laterally within the network. Implement strict ingress and egress rules to control data flow.

1. **Proactive Vulnerability Management**:

   - **Principle**: Stay ahead of potential threats by proactively identifying and addressing vulnerabilities.
   - **Implementation**: Regularly scan for vulnerabilities using automated tools. Maintain an up-to-date inventory of all software components and dependencies. Subscribe to vulnerability databases and security advisories to stay informed about the latest threats and mitigation strategies.

1. **User Education and Awareness**:

   - **Principle**: Empower users with knowledge to prevent security breaches.
   - **Implementation**: Provide regular security training and resources to users. Educate users on best practices for password management, phishing avoidance, and secure coding practices. Encourage a culture of security awareness and proactive reporting of suspicious activities.

1. **Secure Development Practices**:

   - **Principle**: Integrate security into the development lifecycle.
   - **Implementation**: Adopt secure coding standards and practices. Use automated security testing tools as part of the continuous integration/continuous deployment (CI/CD) pipeline. Perform regular security code reviews and threat modeling exercises.

1. **Compliance and Auditing**:

   - **Principle**: Ensure adherence to relevant security standards and regulations.
   - **Implementation**: Align with industry standards such as ISO 27001, GDPR, and other applicable regulations. Maintain detailed logs and records of security-related activities. Conduct regular audits to verify compliance with security policies and standards.
