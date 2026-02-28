# Native Deployment Blockers Analysis

This document analyzes applications that cannot currently be deployed using Hop3's native deployment approach and must use Docker containers instead.

## Executive Summary

Out of 37 applications tested, 3 cannot be deployed natively due to runtime version requirements or build tooling constraints. These applications require either:
- Node.js >= 20 (server has 18.19.1)
- Specialized build tools (pnpm for monorepos)

Note: SonarQube was previously blocked due to Java 21 incompatibility, but this has been resolved with version 26.x.

## Blocked Applications

### 1. Umami (Web Analytics)

**Version:** 3.0.3
**Category:** Analytics
**Blocking Issue:** Node.js version incompatibility

**Technical Details:**
- Umami 3.x uses Next.js 15.x which requires Node.js >= 20.9.0
- Dependencies with Node.js 20+ requirements:
  - `next@16.1.6` - requires `node >= 20.9.0`
  - `cross-env@10.1.0` - requires `node >= 20`
  - `lint-staged@16.2.7` - requires `node >= 20.17`

**Error Message:**
```
npm WARN EBADENGINE Unsupported engine {
  package: 'next@16.1.6',
  required: { node: '>=20.9.0' },
  current: { node: 'v18.19.1', npm: '9.2.0' }
}
```

**Solutions:**
1. **Upgrade Node.js on server** - Install Node.js 20 LTS or 22 LTS
2. **Use Docker deployment** - Docker-based config already exists
3. **Use older Umami version** - Umami 2.x works with Node.js 18 (but loses features)

---

### 2. Uptime Kuma (Monitoring)

**Version:** 2.1.3
**Category:** Monitoring
**Blocking Issue:** ESM module compatibility with Node.js 18

**Technical Details:**
- Uptime Kuma 2.x has dependencies using ES Modules (ESM)
- The `@noble/curves` package (used by `nostr-tools`) is ESM-only
- Node.js 18's CommonJS loader cannot `require()` ESM modules

**Error Message:**
```
Error [ERR_REQUIRE_ESM]: require() of ES Module
/home/hop3/apps/uptime-kuma/src/node_modules/@noble/curves/secp256k1.js
from /home/hop3/apps/uptime-kuma/src/node_modules/nostr-tools/lib/cjs/index.js
not supported.
```

**Solutions:**
1. **Upgrade Node.js on server** - Node.js 20+ has better ESM/CJS interop
2. **Create Docker-based config** - No docker-based config exists yet
3. **Use older Uptime Kuma version** - Version 1.23.x works with Node.js 18 (but loses features)

---

### 3. SonarQube (Code Quality) - RESOLVED

**Version:** 26.2.0.119303 (previously tested with 10.4.1)
**Category:** DevOps / Code Analysis
**Status:** Now works - requires Java 21

**Previous Issue (v10.x):**
- SonarQube 10.x used `java.lang.System.setSecurityManager()` for plugin sandboxing
- Java 21 removed the Security Manager API
- SonarQube 10.x required Java 17

**Resolution:**
- Updated to SonarQube 26.2.0.119303 which **requires** Java 21
- Docker Dockerfile updated to use `openjdk-21-jre-headless`
- Native deployment works since server already has Java 21
- Both native-based and docker-based configurations updated

---

### 4. Formbricks (Survey Platform)

**Version:** 3.17.1
**Category:** Surveys / Forms
**Blocking Issue:** Monorepo requiring pnpm build tooling

**Technical Details:**
- Formbricks is a Turborepo/pnpm monorepo with multiple packages
- Build requires `pnpm` (not npm) for workspace management
- Complex build pipeline with multiple apps (`apps/web`, `apps/docs`, etc.)
- Build times exceed 10 minutes

**Error Message:**
```
Error: Cannot find module '/home/hop3/apps/formbricks/src/apps/web/server.js'
```
(Build never completes, server.js is not generated)

**Solutions:**
1. **Add pnpm support to Hop3** - Install pnpm and detect pnpm-lock.yaml
2. **Use Docker deployment** - Docker-based config already exists
3. **Pre-build artifacts** - Ship pre-built Next.js standalone output

---

## System Requirements Summary

| Application   | Current Requirement | Server Has      | Gap                    |
|---------------|---------------------|-----------------|------------------------|
| Umami 3.x     | Node.js >= 20.9.0   | Node.js 18.19.1 | Need Node.js upgrade   |
| Uptime Kuma 2.x| Node.js >= 20      | Node.js 18.19.1 | Need Node.js upgrade   |
| SonarQube 26.x| Java 21 (required)  | Java 21         | **RESOLVED** - v26.x requires Java 21 |
| Formbricks    | pnpm                | npm only        | Need pnpm support      |

## Recommended Actions

### Short-term (Use Docker)

For immediate deployment needs, use the Docker-based configurations:
- `docker-based/umami/` - Works with current setup
- `docker-based/sonarqube/` - Works with current setup
- `docker-based/formbricks/` - Works with current setup
- Create `docker-based/uptime-kuma/` - Needs to be created

### Medium-term (Upgrade Runtimes)

1. **Upgrade Node.js to v20 LTS or v22 LTS**
   - This would unblock: Umami, Uptime Kuma
   - Node.js 18 reaches end-of-life in April 2025
   - Node.js 20 LTS is supported until April 2026
   - Node.js 22 LTS is supported until April 2027

2. **Install Java 17 as alternative runtime**
   - This would unblock: SonarQube
   - Use `update-alternatives` to manage multiple Java versions
   - Set `JAVA_HOME` per-application in hop3.toml

### Long-term (Enhance Hop3)

1. **Multi-version runtime support**
   - Allow apps to specify required Node.js/Java version in hop3.toml
   - Use tools like `nvm`, `asdf`, or `mise` for version management
   - Example: `[build] node-version = "20"`

2. **pnpm/yarn support**
   - Detect `pnpm-lock.yaml` and use pnpm automatically
   - Detect `yarn.lock` and use yarn automatically
   - Add `package-manager` option to hop3.toml

3. **Pre-built artifact deployment**
   - Support deploying pre-built artifacts (e.g., Next.js standalone)
   - Skip build step entirely for production deployments
   - Useful for complex builds that exceed reasonable timeouts

## Appendix: Test Results

**Native Deployment Results (as of 2026-02-28):**
- Total apps tested: 30 (after removing 3 incompatible apps)
- SonarQube 26.x now included (supports Java 21)

**Apps removed from native-based:**
- umami → use docker-based (requires Node.js >= 20.9.0)
- uptime-kuma → needs docker-based config (requires Node.js >= 20)
- formbricks → use docker-based (requires pnpm)
