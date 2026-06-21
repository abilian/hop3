# Deploying Static Sites on Hop3

A *static site* is a directory of files — HTML, CSS, JavaScript, images — that Hop3 serves directly through nginx. There is no application process and no `$PORT`: requests are answered straight from disk, which makes static sites the simplest and most robust thing you can run on Hop3.

This page explains the concepts shared by every static deployment. Each tutorial below is a complete, runnable walkthrough for one tool; read this first to choose your approach, then follow the guide that matches it.

## Two ways to deploy

Whatever generator you use (or none at all), there are only two strategies. The difference is **where the site is built**.

| | **Build at the source** | **Build on the server** |
|---|---|---|
| Where the generator runs | Your machine, or CI | The Hop3 server, on every deploy |
| What you deploy | The finished files (the output directory) | Your source |
| Server-side build step | None | `before-build` runs the generator |
| Toolchain on the server | None needed | The generator's runtime (Node, Ruby, Hugo, …) |
| Best when | You build in CI, the build needs secrets/tools you'd rather keep off the server, or builds are heavy | You want `git push`-style deploys and a simple, reproducible build |

Both end the same way: a directory of static files served by nginx. **Build at the source** is the simplest and is covered by the [Plain static site](static-site.md) guide — point Hop3 at your output directory and you are done. **Build on the server** is what the per-generator guides below show.

> Either strategy can be used with any generator. To use *build-at-source* with Hugo/Astro/Eleventy/Jekyll, run its build locally and deploy the output exactly like a [plain static site](static-site.md). To use *build-on-server*, follow the generator's guide.

## Declaring a static site

You tell Hop3 to serve a directory as static by pointing it at that directory. Two equivalent declarations work — **a `Procfile` is not required**:

```toml
# hop3.toml  (recommended)
[run.workers]
static = "public"      # the directory to serve
```

```text
# Procfile  (equivalent)
static: public
```

Either way, Hop3 skips the language toolchains and application servers and configures nginx to serve that directory directly. If both files declare a static directory, **`hop3.toml` wins** — it is Hop3's own config, whereas a `Procfile` is a generic convention other tools may use. For *build-on-server*, pair it with a build step — e.g. `[build]` `before-build = ["npm run build"]` producing `dist/`, then serve `dist/`.

## The deploy workflow is always the same

Every static tutorial uses the same four-step flow, so once you have learned one you have learned them all:

1. **Deploy** — `hop3 deploy --app <app>` (the first deploy creates the app).
2. **Set the hostname** — `hop3 config set --app <app> HOST_NAME=<app>.<your-domain>`.
3. **Apply it** — deploy once more so nginx picks up the hostname.
4. **Verify** — `hop3 app status --app <app>` and `curl` the site.

Managing a static app is the same as any Hop3 app: `hop3 app logs`, `hop3 app restart`, `hop3 config show`, `hop3 app destroy`.

## Choose a guide

| Guide | Tool | Language | Typical output dir |
|-------|------|----------|--------------------|
| [Plain static site](static-site.md) | none (pre-built files) | — | `public/` |
| [Hugo](hugo.md) | Hugo | Go (single binary) | `public/` |
| [Astro](astro.md) | Astro | Node.js | `dist/` |
| [Eleventy](eleventy.md) | Eleventy (11ty) | Node.js | `_site/` |
| [Jekyll](jekyll.md) | Jekyll | Ruby | `_site/` |

Start with [Plain static site](static-site.md) if you already have built files (or want the build-at-source strategy); otherwise pick the generator you author your content with.
