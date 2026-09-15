# Annexe I: Project plan Nix Integration for Hop3

Hop3 is an open-source orchestration platform that simplifies the deployment and management of distributed applications across cloud and edge environments. It gives developers and small organisations full control of their IT infrastructure and data, for digital sovereignty and avoiding vendor lock-in, with an emphasis on flexibility, security, resilience, and ease of use.

You can find a recent (updated) presentation here: https://speakerdeck.com/sfermigier/hop3-simplifying-cloud-and-self-hosting-for-developers-and-smes

The project will enhance the Hop3 platform by integrating Nix, a package manager that creates reproducible environments, to improve flexibility at build time and consistency at run time. As a test bed and showcase of this integration, we will package 20 diverse F/OSS applications. We will also develop resilience and cybersecurity features for the platform.

The plan outlined below is a slight rewrite of the last plan submitted by email on Sep 18, 2024. We split what was "WP2" in our email into T2 and T3. We have also split WP3 (now T4) into 4 milestones / deliverables. Nothing else has changed, including the amounts we had provided in September.

## T1 - Nix Build Plugins for Hop3

The project will enhance Hop3 by integrating the Nix package manager to provide reproducible environments and improve flexibility at build time. This will expand the concept of "builder" in Hop3 with additional or alternative builders, all built on Nix.
Deliverables include a Nix "native" builder for applications that already have a Nix expression, for instance in the Nixpkgs repository, so existing Nix expressions integrate into Hop3's build workflow and metadata system. The project will also create or integrate Nix-based alternatives for applications without Nix configurations, wrapping native build processes (e.g., pip, npm, mvn) with tools like Dream2nix so they fit Hop3's build and deployment ecosystem.

Milestone(s)

• M1.1 Nix "native" builder (for integrating apps described by a Nix expression)
• M1.2 Nix alternatives to all the existing builders (at least: Python, Nodejs, Ruby, Go, Rust,
Java) for a "12-Factor App"-style workflow
Amount

## T2 - Nix Runtime

The project will extend Hop3 by using Nix to create and manage runtime environments for application workers. Applications will run consistently and reproducibly, with isolation that limits interference between workloads and strengthens security. Nix will complement Hop3's existing and upcoming support for diverse execution environments, including lightweight Linux isolation, containers, lightweight VMs, full VMs, edge, IoT devices, and bare-metal setups.

Milestone(s)

• M2.1 Specifications and Proof of Concept
• M2.2 Beta implementation
• M2.3 Final release ("1.0")


## T3 - Security & Resilience

We will improve Hop3's resilience and security with new features and tools. This includes integrating backing services like storage, email, and databases, in line with the 12-Factor App methodology. Upgrade mechanisms will handle platform and application updates, with a focus on safe data migrations. Automated backups will enable restoration and migration across servers or clusters, validated through resilience and migration tests. A testing framework will include end-to-end deployment and runtime-specific canary tests to verify application health and to exercise the whole application lifecycle. Security will be strengthened with network-level firewalls and a Web Application Firewall (WAF) using tools like OWASP Core Ruleset and Coraza. We will redesign the current Command-Line Interface (CLI) for a better developer and devops experience, and build a basic web-based User Interface (UI) so non-technical users can interact with Hop3 visually.

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

Package 20 popular or useful open-source applications to run on Hop3, covering a wide range of functional domains, application types and backing technologies. It will validate the other deliverables as they land and give end users production-ready applications. The work will include writing the declarative configurations, tests, and possibly patches, and documenting the process. Experience reports will record issues and lessons learned during packaging and guide future efforts. Packaging is iterative: the initial packages will keep evolving as the platform gains or improves features.

Milestone(s)

• M4.1 - 5 first applications + experience reports
• M4.2 - 5 next applications + experience reports
• M4.3 - 5 next applications + experience reports
• M4.4 - 5 last applications + experience reports

## T5 - Dissemination & Engagement

Dissemination brings Hop3 adoption, community contributions and recognition. We will promote it through an enriched website and blog with regular updates, documentation for developers, administrators, and end-users, and a technical report or research paper on project outcomes. We will present at conferences such as OW2Con, OSXP, FOSDEM, or NixCon to show progress and attract contributors. Videos, live office hours, and social media will add instructional content and real-time support, and help build an active community around Hop3.

Milestone(s)

• M5.1 Website, blog (structure & regular content updates):
• M5.2 Documentation (for devs, admins, end-users):
• M5.3 Technical report and/or research paper:
• M5.4 Conference presentation or workshop
• M5.6 Videos/screencasts
