# Open Questions

(For more in-depth architectural discussions, check the [ADRs](https://github.com/abilian/hop3/tree/main/notes/adrs))

## Compliance

- Do we support both SPDX and CycloneDX SBOMs?
- How do we validate / visualize SBOMs?

**Note:** The `sbom` command is planned (listed in CLI completion) but not yet implemented.

---

## Resolved Questions

### Tooling
- ~~Do we keep `duty`?~~ **Resolved:** No, duty is no longer used.

### Plugins
- ~~Do we keep using `pluggy` or switch to `plux`?~~ **Resolved:** Using pluggy.
- ~~Do we introduce a registry (à la `flask-super`)?~~ **Resolved:** Using Dishka DI with pluggy hooks.
