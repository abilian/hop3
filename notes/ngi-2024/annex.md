# Annexe I: Project plan Nix Integration for Hop3

Hop3 is an open-source orchestration platform designed to simplify the deployment and management of distributed applications across cloud and edge environments. With a focus on flexibility, security, resilience, and ease of use, Hop3 empowers developers and small organisations to take full control of their IT infrastructure and data, ensuring digital sovereignty and avoiding vendor lock-in.

You can find a recent (updated) presentation here: https://speakerdeck.com/sfermigier/hop3- simplifying-cloud-and-self-hosting-for-developers-and-smes

The project will enhance the Hop3 platform by integrating Nix, a powerful package manager known for its ability to create reproducible environments, to improve build-time flexibility and ensure consistent, reliable run-time performance. As a test bed and showcase of this integration, we will package 20 diverse and impactful F/OSS applications. Additionally, we will develop new resilience and cybersecurity features to further strengthen the platform's robustness and security.

The plan outlined below is a slight rewrite of the last plan submitted by email on Sep 18, 2024. We split what was "WP2" in our email into T2 and T3. And we have split WP3 (now T4) into 4 milestones / deliverables. Nothing else has changed, including the amounts we had provided in September.

## T1 - Nix Build Plugins for Hop3

The project will enhance Hop3 by integrating the Nix package manager to provide reproducible environments and to improve build-time flexibility and reliability. This will expand the concept of "builder" in Hop3 to provide additional or alternative builders, all leveraging the Nix technology.
Deliverables include developing a Nix "native" builder for applications with an existing Nix expression, for instance when they are already in the Nixpkgs repository, to incorporate existing Nix expressions into Hop3’s build workflow and metadata system. Additionally, the project will create or integrate Nix-based alternatives for applications lacking Nix configurations by encapsulating native build processes (e.g., pip, npm, mvn) using tools like Dream2nix, ensuring smooth integration with Hop3’s build and deployment ecosystem.

Milestone(s)

• M1.1 Nix "native" builder (for integrating apps described by a Nix expression) 
• M1.2 Nix alternatives to all the existing builders (at least: Python, Nodejs, Ruby, Go, Rust,
Java) for "12 Factor App" like workflow 
Amount

## T2 - Nix Runtime

The project will extend Hop3 by integrating Nix as a powerful foundation for creating and managing runtime environments for application workers. This integration will ensure consistency, reproducibility, and reliability in how applications are executed, while providing robust isolation to minimize workload interference and enhance security. Nix will complement Hop3’s existing and upcoming support for diverse execution environments, including lightweight Linux isolation, containers, lightweight VMs, full VMs, edge, IoT devices, and bare-metal setups. By offering Nix as an additional or alternative runtime, the platform will provide users with a versatile and future-proof solution tailored to various deployment scenarios.

Milestone(s)

• M2.1 Specifications and Proof of Concept 
• M2.2 Bêta implementation 
• M2.3 Final release ("1.0") 


## T3 - Security & Resilience

We will enhance Hop3's resilience and security by introducing robust features and tools. This includes integrating essential backing services like storage, email, and databases in alignment with the 12-Factor App methodology. Upgrade mechanisms will ensure seamless platform and application updates, with a focus on safe data migrations. Automated backups will enable reliable restoration and migration across servers or clusters, validated through resilience and migration tests. A comprehensive testing framework will include end-to-end deployment and runtime-specific canary tests to verify application health, and also that the whole application lifecycle is thoroghly tested. Security will be fortified with network-level firewalls and a Web Application Firewall (WAF) using tools like OWASP Core Ruleset and Coraza. We will redesign the current Command-Line Interface (CLI) optimizing UX for developers and devops, and create a basic web-based User Interface (UI) for non-technical users to interact with Hop3 visually.

Milestone(s)

• M3.1 Backing services (storage, email...): 
• M3.2 Upgrades (including data migrations) 
• M3.3 Backups (including resilience and migration tests): 
• M3.4 Testing framework and infrastructure: 
• M3.5 Firewalls (network-level and WAF): 
• M3.6 CLI (basic) 
• M3.7 Web UI (basic) 
• M3.8 Process outcomes of security audit and accessibility scan 

## T4 - Packaged Applications

Package 20 popular or useful open-source applications to run on Hop3, covering a large range of functional domains, applications types and backing technologies. This will serve as progessive validation and demonstration of the other deliverables, but also provide robust products for end- users of the platform. This will also include writing the necessary declarative configurations, tests, and possibly patches, and documenting the process. Experience reports will be generated to capture any issues, challenges, or lessons learned from the packaging process, and will act as a guide for future similar efforts. This will be an iterative effort, in the sense that the initial packages will continue to evolve, if necessary, with additional or enhanced features of the platform.

Milestone(s)

• M4.1 - 5 first applications + experience reports 
• M4.2 - 5 next applications + experience reports 
• M4.3 - 5 next applications + experience reports 
• M4.4 - 5 last applications + experience reports 

## T5 - Dissemination & Engagement

Effective dissemination is critical for the success of Hop3 as an Open Source platform, ensuring adoption, community contributions and recognition within the industry.
This task focuses on promoting Hop3 through an enriched website and blog with regular updates, comprehensive documentation for developers, administrators, and end-users, and a technical report or research paper highlighting project outcomes. It includes presenting at industry events like OW2Con, OSXP, FOSDEM, or NixCon to showcase progress and attract contributors. Additionally, videos, live office hours, and social media engagement will provide instructional content and real-time support, fostering a strong and active community around Hop3.

Milestone(s)

• M5.1 Website, blog (structure & regular content updates): 
• M5.2 Documentation (for devs, admins, end-users): 
• M5.3 Technical report and/or research paper: 
• M5.4 Conference presentation or workshop 
• M5.6 Videos/screencasts 

