# Experience Report: Jenkins

**Status:** Draft (0.5)
**App:** Jenkins — CI/CD server
**Language:** Java
**Database:** None
**Website:** https://www.jenkins.io/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/generic
- **Addons:** None
- **Build steps:** Pre-built WAR file download (no source compilation)
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** java-war
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** java-war
- **Key config:** JDK 17, JENKINS_HOME setup
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** None
- **Status:** Passing
- **Issues:** None

## Lessons Learned

- WAR files are self-contained deployment units similar to Go binaries: a single artifact with all dependencies bundled.
- The java-war template handles JDK provisioning automatically, removing the need to manually manage Java installations.
- JAVA_OPTS for memory limits (e.g., -Xmx) are important in production to prevent Jenkins from consuming all available memory.
- JENKINS_HOME must be set to a writable persistent directory to preserve configuration, jobs, and build history across restarts.

## Cross-Method Comparison

All four methods are straightforward since Jenkins ships as a single WAR file with no external database dependency. The java-war Nix template is the cleanest approach as it handles both JDK provisioning and JENKINS_HOME setup declaratively, while native and Docker methods require manual JDK management.
