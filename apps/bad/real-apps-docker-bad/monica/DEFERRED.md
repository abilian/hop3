# Monica (Docker) — Deferred

**Status:** deferred from the 0.5 test suite.
**Moved:** 2026-04-13

## Blocker

Monica v4.x ships a `webpack.mix.js` config whose `ProgressPlugin`
receives `reporter` / `reporters` options as shorthand properties
inside a destructured function call. Webpack 5's strict schema
validator rejects these outright:

```
options has an unknown property 'reporter'. These properties are valid:
  object { activeModules?, dependencies?, dependenciesCount?, entries?,
  handler?, modules?, modulesCount?, percentBy?, profile? }
```

Tried and didn't fix it:
- Bumping `v4.0.0` → `v4.1.2` (same Mix version)
- Installing Node 18 from NodeSource (the webpack check doesn't
  depend on Node version)
- `sed`-patching the property out of the Mix JS
  (the option is passed via shorthand from a helper function, not
  as a literal `key: value` pair — sed can't reach it)

## Unblocker for 0.6

- Monica v5.0.0+ (currently beta) switches to Vite and drops
  Laravel Mix entirely. Once stable, retry this Dockerfile with
  `MONICA_VERSION=v5.0.0` and the npm build should work on modern
  Node.
- Alternative: build Monica outside Docker (use a CI step that
  produces a tarball with pre-compiled assets) and have the
  Dockerfile just pull that tarball.

## How to reintroduce

Move back to `apps/real-apps-docker/monica/` when:
1. Monica v5 is released (watch
   https://github.com/monicahq/monica/releases)
2. OR someone wants to maintain a patched Mix config in this repo
