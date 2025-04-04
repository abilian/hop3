# Compliance Directory

This directory contains files related to software compliance, dependency management, and security. Below is an overview of the files:

## Files

These files are automatically generated by the `make generate-sbom` command.

### `sbom-cyclonedx.json`
- **Description:** SBOM in CycloneDX format, detailing components and dependencies.
- **Use Case:** Supply chain security and compliance audits with the CycloneDX ecosystem.

### `sbom-spdx.json` [NB: NOT WORKING YET]
- **Description:** SBOM in SPDX format for license tracking and compliance.
- **Use Case:** Licensing audits and interoperability with SPDX tools.

### `requirements-full.txt`
- **Description:** Comprehensive list of all dependencies for all environments.
- **Use Case:** Provided for reference and when using certains tools. The recommended approach is to use `uv sync` to manage dependencies.

### `requirements-prod.txt`
- **Description:** Minimal list of dependencies for production.
- **Use Case:** Provided for reference and when using certains tools. The recommended approach is to use `pip install .` to manage dependencies.

## Usage and Best Practices

- Regularly update SBOMs and dependency files.
- Use security tools (e.g., Dependency-Track) for audits.
- Validate SBOMs with, e.g.:
  ```bash
  cyclonedx-cli validate --input-file sbom-cyclonedx.json
  spdx-tool verify sbom-spdx.json
  ```
  (Note: this needs third-party tools to be installed.)
