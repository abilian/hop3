# Hop3 Core Values and Design Principles

Hop3 is an open-source project designed to simplify the deployment and management of web applications and services across a variety of environments, from low-end devices to cloud and edge computing platforms. At its core, Hop3 embodies principles of efficiency, inclusivity, and simplicity, aiming to make advanced technology accessible to a broad audience including individual developers, hobbyists, educational institutions, and small to medium enterprises.

With a focus on leveraging standard tooling and minimizing dependencies, Hop3 adheres to the 12-factor app methodology to ensure applications are portable, scalable, and maintainable. The project is built on a foundation of readable and functional code, emphasizing user-centric design to cover a wide range of use cases with sensible defaults and flexible configuration options.

Hop3's architecture is designed to be open and extensible, encouraging community contributions and the development of plugins to extend its core functionality. By prioritizing modern security practices, backward compatibility, and support for major Linux distributions, Hop3 aims to provide a reliable and future-proof platform that promotes sustainable digital practices and fosters an inclusive open-source community.

## Core Principles and Values

1. **Efficiency Across Environments**: Optimized for performance not only on low-end devices but also in cloud (small to large VM, bare metal) and edge computing environments, ensuring broad accessibility and adaptability.

2. **Inclusivity in Technology**: Designed to be accessible to individual developers, hobbyists, K-12 schools, and small to medium enterprises, promoting digital literacy and innovation across diverse communities.

3. **Simplicity in Code**: Strives for maintainable codebase, through a modular and plugin-oriented architecture, ensuring that each component is easy to understand and maintain. This approach allows developers to focus on specific areas of the platform without being overwhelmed by its entirety, promoting clarity and efficiency in development.

4. **Minimal Dependencies**: Maintains a lean architecture with minimal external dependencies to ensure reliability, ease of installation, and straightforward updates.

5. **Adherence to 12-Factor App Methodology**: Embraces the principles of the 12-factor app to promote portability, scalability, and a seamless development-to-deployment workflow.

6. **User-Centric Design**: Focuses on simplifying the user experience, from setup to deployment, ensuring that common use cases are intuitive and well-supported.

7. **Broad Use Case Coverage**: Aims to address a wide range of deployment scenarios, covering the most common needs with sensible defaults and flexible configuration options.

8. **Integration with Standard Ecosystems**: Leverages widely-used tools and platforms (e.g., Git, SSH) and supports major Linux distributions, ensuring compatibility and ease of use across different environments.

9. **Modern and Secure Defaults**: Provides sensible, secure defaults for all features, with a focus on modern security practices and compliance standards.

10. **Open and Extensible**: Encourages community contributions and extensions through a plugin architecture, allowing for the integration of additional services and tools as needed.

11. **Backward Compatibility and Future-Proofing**: Balances innovation with the preservation of backward compatibility, ensuring long-term viability and support for legacy systems where feasible.

12. **Sustainability and Openness**: Promotes sustainable digital practices and open-source collaboration, contributing to a resilient and inclusive future for the internet.


## Hop3 and the 12-Factor App Methodology

The 12-factor app methodology is a set of practices for building modern web applications to ensure they are portable, scalable, and maintainable in a Platform-as-a-Service (PaaS) environment. Hop3 aligns with these principles to provide a robust and efficient platform for deploying web applications, promoting best practices in development and operations. 

1. **Codebase** - One codebase tracked in version control with many deploys. Hop3 encourages a single codebase for each application, version-controlled with Git, allowing for multiple deployments across different environments.

2. **Dependencies** - Explicitly declare and isolate dependencies. Hop3 supports virtual environments, ensuring all dependencies are explicitly declared and isolated.

3. **Config** - Store configuration in the environment. Hop3 allows environment variables to be defined in a separate `ENV` file or through the platform's configuration tools, keeping sensitive and environment-specific configurations out of the code.

4. **Backing Services** - Treat backing services as attached resources. Hop3's plugin architecture can support the integration of external services (like databases, messaging systems, etc.) as attached resources, allowing for easy swap and reconfiguration without code changes.

5. **Build, release, run** - Strictly separate build and run stages. Hop3 can automate the build process with CI/CD pipelines, creating immutable releases that are then deployed, ensuring a clear separation between build, release, and run stages.

6. **Processes** - Execute the app as one or more stateless processes. Hop3 encourages stateless application design, where any required state is stored in a backing service, ensuring scalability and resilience.

7. **Port binding** - Export services via port binding. Applications deployed with Hop3 can bind to a given port provided by the environment for HTTP services, adhering to the principle of self-contained services.

8. **Concurrency** - Scale out via the process model. Hop3's underlying technologies (like uWSGI for Python applications) support process-based scaling, allowing applications to handle multiple concurrent requests efficiently.

9. **Disposability** - Maximize robustness with fast startup and graceful shutdown. Hop3 supports and encourages applications that can be quickly started and gracefully shut down, making them robust and minimizing downtime during scaling and deployment.

10. **Dev/prod parity** - Keep development, staging, and production as similar as possible. Hop3's deployment methodology and support for environment variables make it easier to maintain parity across different environments, reducing "works on my machine" issues.

11. **Logs** - Treat logs as event streams. Hop3 can be configured to treat logs as event streams, pushing them to a centralized logging service for analysis, without requiring changes to the application code.

12. **Admin processes** - Run admin/management tasks as one-off processes. Hop3 can execute administrative or maintenance tasks as one-off processes, either through direct command execution or through the platform's task scheduling mechanisms.
