# Deploying JavaScript / Node.js on Hop3

A Node.js app on Hop3 is a long-running process: Hop3 installs your npm dependencies, runs any build step, then starts your server and keeps it alive. Your app listens on the port Hop3 hands it through `$PORT`, and nginx sits in front as the reverse proxy, terminating HTTP for your hostname and forwarding requests to that process. You write the same `app.listen(process.env.PORT)` you would write anywhere; Hop3 handles the toolchain, the proxy, and the process supervision.

This page covers what every Node.js deployment on Hop3 has in common. Each tutorial below is a complete walkthrough for one framework — read this first, then pick the guide that matches your stack.

## How Hop3 builds and runs Node.js

Hop3 detects a Node.js app (a `package.json` in the repo) and uses its Node toolchain. You request the runtime explicitly under `[build].packages` (`nodejs`, and `npm` if you list dependencies separately), and the build is driven by `[build].before-build` — typically `npm install`, plus a `npm run build` for frameworks that compile (TypeScript, bundlers, SSR).

The app is started by `[run].start`, which must launch a process that **binds to `$PORT`** — the dynamic port Hop3 assigns. Never hard-code `3000`; always read `process.env.PORT`. Hop3 supervises that process (restarting it if it dies) and points nginx at it. nginx is the only thing exposed publicly; your Node process only ever talks to the loopback port Hop3 gave it.

A representative `hop3.toml` for a plain Node service looks like this:

```toml
[metadata]
id = "my-node-app"
version = "1.0.0"

[build]
before-build = ["npm install"]
packages = ["nodejs", "npm"]

[run]
start = "node app.js"

[env]
NODE_ENV = "production"

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

A `Procfile` is supported as an equivalent (`web: node app.js`, with `prebuild:` for the install step), but `hop3.toml` is the recommended, more expressive form, and it wins when both are present.

## Notes that apply across all frameworks

- **Bind to `$PORT`.** This is the single most common deploy bug. `const port = process.env.PORT || 3000` works locally and in production. For frameworks that pin a host, also bind `0.0.0.0` (e.g. Next.js standalone needs `HOSTNAME=0.0.0.0`).
- **Build step for compiled stacks.** TypeScript frameworks (NestJS) and SSR frameworks (Next.js, Nuxt) need `npm run build` in `[build].before-build`, and `[run].start` then points at the compiled output — `node dist/main.js` for NestJS, `node .next/standalone/server.js` for Next.js. Plain JS (Express, Fastify) skips the build and runs the source directly.
- **Production vs dev dependencies.** Anything needed at runtime must live in `dependencies`, not `devDependencies`. Using `npm install --production` keeps the build lean — but only if your build doesn't need dev tools (a TypeScript compile does, so don't combine `--production` with a `npm run build` that uses `tsc`).
- **Addons inject env vars.** Attaching a Postgres addon sets `DATABASE_URL`; a Redis addon sets `REDIS_URL`. Read them with `process.env.DATABASE_URL` — no connection string lives in your code. Set app secrets with `hop3 config set --app <app> KEY=value`.
- **Health checks.** Expose a cheap endpoint (`/up` returning `200 OK`) and declare it under `[healthcheck]` so Hop3 knows the app is actually serving, not just running.
- **`before-run` for runtime prep.** Use `[run].before-run` for steps that must happen each start — database migrations (`npx prisma migrate deploy`), or copying static assets into a standalone bundle.

## Choose a framework

| Framework | Tutorial | What it's for |
|-----------|----------|---------------|
| Express | [express.md](express.md) | The classic minimal web framework — a single `node app.js` process, no build step. |
| Fastify | [fastify.md](fastify.md) | A faster, schema-first alternative to Express, deployed the same way. |
| NestJS | [nestjs.md](nestjs.md) | Opinionated enterprise TypeScript framework; builds to `dist/`, runs `node dist/main.js`. |
| Next.js | [nextjs.md](nextjs.md) | React with server-side rendering; standalone build, runs `node .next/standalone/server.js`. |
| Nuxt.js | [nuxtjs.md](nuxtjs.md) | Vue's SSR framework; built output served by a long-running Node process. |

If you're new to Hop3, start with [Express](express.md) — it's the simplest end-to-end deploy and the patterns carry over to every other framework here.
