# Changelog

All notable changes to this project will be documented in this file.

## [0.4.0] - Unreleased

### <!-- 0 -->🚀 Features

-   **CLI/Server Architecture**: Introduced a new server-based architecture where the `hop3-cli` communicates with a central `hop3-server` via JSON-RPC. Includes an option for a secure SSH tunnel.
-   **Web Server & UI**: Added initial scaffolding for a future web server and front-end management interface.
-   **Backups & SBOM**: Implemented a basic application backup mechanism and an automatic generator for Software Bill of Materials (SBOM) to enhance supply chain security.
-   **CLI Enhancements**: Improved the command-line interface with a more robust help system and a proof-of-concept for a new command parser.

### <!-- 1 -->🐛 Bug Fixes

-   Corrected an issue with the `Config` object constructor.
-   Fixed a bug that was breaking the Python application builder.
-   Repaired issues in the server installer and dependency resolution.

### <!-- 2 -->🚜 Refactor

-   **Major Repository Reorganization**: The project has been restructured into a monorepo with distinct sub-packages, including `hop3-cli`, `hop3-server`, `hop3-agent`, and `hop3-testing`.
-   **Plugin Architecture**: Began a significant refactoring to make core components more modular and plugin-oriented.
-   **Configuration System**: Overhauled configuration handling, moving from hardcoded constants to a more flexible, class-based system.
-   **Code Modernization**: Replaced many string-based paths with `pathlib.Path` objects and modernized command execution using `subprocess.run`.
-   **Nginx & Certificates**: Refactored the management of Nginx configurations and SSL certificates for better maintainability.

### <!-- 3 -->📚 Documentation

-   Added an Open Source Compliance Program document and a guide for project evangelism.
-   Created several Architecture Decision Records (ADRs) to document key design choices.
-   General improvements to READMEs, docstrings, and comments across the codebase.

### <!-- 6 -->🧪 Testing

-   Enabled end-to-end (e2e) tests to run in the Continuous Integration pipeline.
-   General cleanup and refactoring of the test suite to fix warnings and improve reliability.

### <!-- 7 -->⚙️ Miscellaneous

-   **Dependency Management**: Fully migrated the project from Poetry to `uv`, including setting up `uv` workspaces for the new monorepo structure.
-   **CI/CD**: Implemented numerous fixes to CI configurations, improving support for various operating systems and resolving issues with `nox` and `docker` build steps.
-   **Licensing**: The project license has been changed to Apache 2.0.
-   **Code Quality**: Performed extensive code formatting and linting fixes across the entire project to improve consistency and readability.

## [0.3.0] - 2025-03-24

### <!-- 0 -->🚀 Features

-   **Stable Deployments**: First version considered stable enough for deploying simple web applications (Python WSGI and static sites).
-   **Core API**: Introduced the first version of the core internal API for managing application lifecycles.

### <!-- 1 -->🐛 Bug Fixes

-   Stabilized the installation script for production-like environments.
-   Numerous fixes to the deployment process to improve reliability.

### <!-- 2 -->🚜 Refactor

-   Improved core deployment logic for simplicity and robustness.

## [0.2.2] - 2024-07-15

This release focused on laying the groundwork for a web-based management interface and its underlying database model.

### <!-- 0 -->🚀 Features

-   Initiated development of a web application and ORM model (WIP).
-   Added preliminary security features for the upcoming web app.

### <!-- 1 -->🐛 Bug Fixes

-   Addressed key bugs in the installer and static site deployment process.
-   Fixed various typing issues and repaired a broken web deployment mechanism.

### <!-- 2 -->🚜 Refactor

-   Refined the uWSGI manager and cleaned up the actor framework components.

### <!-- 3 -->📚 Documentation

-   Enhanced project documentation by adding security principles to the core values.

## [0.2.1] - 2024-07-04

This was a maintenance and documentation-focused release, improving core networking components and significantly enhancing project documentation.

### <!-- 0 -->🚀 Features

-   Began initial work on a new actor-based framework.

### <!-- 2 -->🚜 Refactor

-   Improved the certificate manager and proxy setup logic.

### <!-- 3 -->📚 Documentation

-   Major updates to project documentation, including the README, architecture descriptions, core values, and docstrings.
-   Configured `git-cliff` for automated changelog generation.

## [0.2.0] - 2024-06-28

A maintenance release primarily focused on overhauling the testing suite and modernizing the Nginx setup.

### <!-- 2 -->🚜 Refactor

-   Modernized the Nginx setup by converting it to a class-based implementation.

### <!-- 6 -->🧪 Testing

-   Major improvements to the testing suite, including fixing and cleaning up unit tests and the end-to-end test harness.

## [0.1.5] - 2024-06-27

A minor release that introduced the official CHANGELOG and performed code cleanup.

### <!-- 1 -->🐛 Bug Fixes

-   Temporarily disabled Nginx configuration checks to work around an issue.

### <!-- 2 -->🚜 Refactor

-   Cleaned up various application configuration files.

### <!-- 3 -->📚 Documentation

-   Added the first version of this `CHANGELOG.md` file.

## [0.1.4] - 2024-06-27

This release focused on improving static site deployments and included a significant effort to enhance the project's documentation and overall presentation.

### <!-- 1 -->🐛 Bug Fixes

-   Addressed errors related to deploying static sites.

### <!-- 3 -->📚 Documentation

-   Extensive updates to the README, project metadata, and roadmap.
-   Added REUSE compliance logo and project branding.

## [0.1.3] - 2024-06-07

A minor maintenance release.

### <!-- 7 -->⚙️ Miscellaneous

-   Updated project dependencies.

## [0.1.2] - 2024-04-19

This release focused on internal refactoring to improve code quality and modernize the codebase.

### <!-- 2 -->🚜 Refactor

-   Performed a major code cleanup using `ruff`, modernizing path handling with `pathlib`, and improving shell command execution.

### <!-- 3 -->📚 Documentation

-   Improved documentation by adding and fixing numerous docstrings.

## [0.1.1] - 2024-04-18

A small release that added a minor feature, fixed a regression, and performed test maintenance.

### <!-- 0 -->🚀 Features

-   Added the ability to sort applications.

### <!-- 1 -->🐛 Bug Fixes

-   Fixed a recent regression.

### <!-- 7 -->⚙️ Miscellaneous

-   Updated dependencies and applied workarounds for failing tests.

## [0.1.0] - 2024-04-11

The foundational release of Hop3: established the project's core architecture, introduced initial features, and set up the first tests and documentation.

### <!-- 0 -->🚀 Features

-   Prototyped initial application builders and started work on addons.
-   Introduced initial support for a SQL-based model (SQLAlchemy) and Postgres.

### <!-- 1 -->🐛 Bug Fixes

-   Addressed initial REUSE compliance issues.

### <!-- 2 -->🚜 Refactor

-   Established the core class-based architecture, moving away from a script-based model.
-   Performed major refactoring of the initial codebase for better structure and typing.

### <!-- 3 -->📚 Documentation

-   Created the initial project `README.md`, roadmap, and compliance documentation.

### <!-- 6 -->🧪 Testing

-   Added the first end-to-end test runner.
