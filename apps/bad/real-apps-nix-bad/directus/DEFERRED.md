# Directus nix — deferred

**Reason:** Directus's published JS build assumes a **pnpm** installation layout. A plain `npm install directus` produces a flat `node_modules/` tree; Directus's prebuilt code references pnpm's content-addressed layout (`node_modules/.pnpm/<scope>_<name>@<version>/…`). When Node tries to resolve those paths against the npm-flat layout, named ESM imports of CommonJS modules fail:

```
SyntaxError: Named export 'Type' not found. The requested module
'../../../node_modules/.pnpm/@sinclair_typebox@0.34.41/node_modules/@sinclair/typebox/build/esm/type/type/index.js'
is a CommonJS module, which may not support all module.exports as named exports.
```

The fix is to install via `pnpm` instead of `npm` at Nix build time. Requires `pkgs.nodePackages.pnpm` (or `pkgs.pnpm`) in `nativeBuildInputs` plus an `__noChroot = true` install phase that runs `pnpm install`.

**Working variant (kept):**

- `apps/real-apps-docker/directus/` — Dockerfile uses npm, which happens to work inside the `node:22 + debian:trixie-slim` image because Directus's npm-published package works when resolved by npm directly, in isolation. (The nix variant failed because wrapping npm-installed Directus in a symlinked `node_modules` under a Nix store path triggers a different module-resolution path.)

**Unblocker:** rebuild the nix variant using pnpm, OR wait for the `node-npm-install` template (Gap 2 in `local-notes/stacks-and-apps/TEMPLATE-LIMITATIONS.md`) to be extended with a pnpm alternative.

This limitation will hit any Directus-flavoured npm package that ships a prebuilt `dist/` assuming pnpm: likely Outline, some Strapi setups, and anything using the @directus family (extensions, SDK).
