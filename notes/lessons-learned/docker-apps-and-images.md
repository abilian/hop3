# Lessons Learned: Containerized Apps and Images

**Updated**: 2026-09-08, consolidated from the internal notes of the December 2025 demo campaign (the first sixty apps, most of them Docker at the time).

This note records what went wrong inside containers and the build policy that came out of it. Network ranges and the `localhost` rewrite live in [`database-addon-portability.md`](./database-addon-portability.md).

## Build from source, on the base the server runs

A native build on the server ranks first. Next comes a Dockerfile that builds from source on `debian:bookworm-slim` (later `trixie-slim`), the same libc and packages the server has. An upstream pre-built image is the last resort. `FROM wordpress:latest` is a shortcut that hides every dependency the app has. Each hidden dependency is a native build that will fail later for an unrecorded reason. The catalog rule that followed forbids upstream images, pins base images by digest, and has the builder reject a tag-only `FROM`.

Building on a distribution base has four consequences:

- **Architecture.** Upstream images are often x86_64 only; the language base images (`python:X-slim`, `node:X-alpine`, `golang:X-alpine`) and a source build are multi-arch, which is what an ARM64 server needs.
- **Language versions.** A base ships one Python, one PHP, one Node. When an app wants a newer one than the base has, pinning an older app release is usually cheaper than a newer runtime: Linkding 1.44 wanted Python 3.13 on a base with 3.11. Version 1.23.1 did not.
- **Adding an apt source does not pin a version.** Apt takes the highest. Ghost 5.x needs Node 18; Trixie ships 20. Adding NodeSource's `node_18.x` repo as a second source changes nothing, because apt still installs 20. Either write `/etc/apt/preferences.d/` to pin the repo, or skip apt and install the official binary tarball. Applies to any Dockerfile for an app with a hard major-version requirement on Node, Python or Ruby.
- **On Trixie, pin `pnpm@8` and do not use `corepack`.** Trixie's Node 20.x patch level does not expose builtins that pnpm 10 and current corepack need. Two symptoms, one cause: `corepack enable` then a pnpm call gives `ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING`; `npm install -g pnpm` (unpinned, so pnpm 10+) gives `ERR_UNKNOWN_BUILTIN_MODULE`. Write `RUN npm install -g pnpm@8`. **The server's Node 22 does not help here.** These are `FROM debian:trixie-slim` builds that install their own Node. The host's version never enters the image. Five catalog recipes still carry the workaround.

## Compose only recreates what it thinks changed

`docker compose up -d` recreates a container when the service definition changes. An environment it reads from an external file can change without it noticing: after an addon attach, the running container kept the old environment. Use `--force-recreate` whenever the environment may have changed underneath a running service.

## Frameworks refuse hostnames they do not know

By default, Sinatra 4 turns on `Rack::Protection::HostAuthorization`. An app reached through a hostname it does not expect answers 403 with `attack prevented by Rack::Protection::HostAuthorization` in its log. Rails has the same guard. An app deployed under a PaaS-assigned hostname must either be told that hostname or told to accept any; check for host validation middleware before blaming the proxy.

## Files copied into an image keep their permissions

`COPY` preserves the source file's mode, so a file readable only by its owner on the build machine is unreadable by the web server in the container: PHP's `Failed opening required '/var/www/html/index.php'` was a permission problem. Use `COPY --chmod=644` for files a server reads and `--chmod=755` for what it executes.

## Dependencies that used to be bundled no longer are

Sinatra 4 needs `rackup` and a server gem in the Gemfile; `webrick` left the Ruby standard library. `Sinatra could not start, the required gems weren't found!` is the whole diagnosis. Read the framework's notes for the major version before packaging it.

## An image that only configures itself through a browser cannot be automated

LinuxServer.io images take their database settings from a first-run web wizard and ignore the environment. There is no way to provision one non-interactively. Build from source, or choose an image that reads its configuration from the environment.

## Log what you expected, what you ran, and what came back

"Application not accessible" was the whole failure report until the check logged the expected content, the exact `curl` command, the exit code and the first kilobyte of the body. The first run with that logging showed a PHP fatal error in the response body. The permission bug above was fixed in minutes. A verifier that prints only its verdict has hidden the evidence; see [`verifying-an-app-works.md`](./verifying-an-app-works.md).

## The checklist, when a container fails

1. `docker logs` first: startup errors, and the 403s from a security middleware.
2. File permissions in the image (`COPY --chmod`).
3. The framework's explicit dependencies for its major version.
4. The framework's security defaults: host authorization, CSRF, `Secure` cookies over plain HTTP.
5. The environment the container actually has, after `--force-recreate`.
