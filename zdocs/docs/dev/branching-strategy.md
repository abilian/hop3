# Hop3 Git Branching Strategy

The Hop3 project uses a structured branching model to ensure both a stable release for users and a clear path for ongoing development. This strategy allows for parallel development of new features, preparation of new releases, and quick maintenance of production code.

## Main Branches

The repository has two long-lived main branches:

### `stable`
*   **Purpose:** This is the production-ready branch. It always contains the latest stable, released version of Hop3.
*   **Users:** End-users who want to install and use Hop3 should clone or check out this branch.
*   **State:** This branch is intended to be highly stable. Direct commits are discouraged; changes are merged in from `release` or `hotfix` branches.
*   **Current Version:** `v0.3.0`

### `devel`
*   **Purpose:** This is the primary development branch. All new features, refactoring, and other ongoing work are integrated here. It represents the "next" version of the software.
*   **Users:** Contributors who want to add new features or fix non-critical bugs should base their work on this branch.
*   **State:** This branch is actively developed and may be unstable at times. All automated tests must pass before code is merged into `devel`.
*   **Current Version:** Work-in-progress towards `v0.4.0`

## Supporting Branches

Several types of short-lived branches are used to manage the development and release process.

### 1. Feature Branches

* **Purpose:** To develop new features or significant refactors.
*   **Branch from:** `devel`
*   **Merge to:** `devel`
*   **Naming Convention:** There is no strict convention, but descriptive names are used (e.g., `refact-certificates`, `feature/sbom-generator`).
*   **Workflow:**
    1.  A contributor forks the repository.
    2.  Creates a new feature branch from the latest `devel`.
    3.  Makes their changes and commits them.
    4.  Submits a Pull Request (PR) to merge their feature branch back into the main repository's `devel` branch.

### 2. Release Branches

*   **Purpose:** To prepare a new production release. This branch is used for stabilization, final testing, documentation updates, and version bumping. No new features are added to a release branch.
*   **Branch from:** `devel`
*   **Merge to:** `stable` (for the official release) and `devel` (to incorporate any stabilization fixes).
*   **Naming Convention:** `release/vX.Y` (e.g., `release/v0.4`).
*   **Workflow:**
    1.  When `devel` is considered feature-complete for the next release, a `release/` branch is created.
    2.  Bug fixes and final tweaks are made on this branch.
    3.  Once stable, the release branch is merged into `stable` and tagged with the version number (e.g., `v0.4.0`).
    4.  The release branch is also merged back into `devel` to ensure any last-minute fixes are not lost.

### 3. Hotfix Branches

*   **Purpose:** To quickly patch a critical bug in a production version.
*   **Branch from:** `stable`
*   **Merge to:** `stable` and `devel`.
*   **Naming Convention:** `hotfix/vX.Y.Z` (e.g., `hotfix/v0.3.1`).
*   **Workflow:**
    1.  A `hotfix/` branch is created from the `stable` branch.
    2.  The critical bug is fixed and committed.
    3.  The branch is merged back into `stable` and tagged with a new patch version.
    4.  It is also merged into `devel` to ensure the fix is included in future releases.

## Summary of the Workflow

*   **Contributors:** Fork the repo, create feature branches from `devel`, and submit Pull Requests back to `devel`.
*   **Users:** Use the `stable` branch for a reliable installation.
*   **Maintainers:** Manage the release cycle by creating `release` branches from `devel` and merging them into `stable` and back into `devel`. Urgent production fixes are handled with `hotfix` branches.
