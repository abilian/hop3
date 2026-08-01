---
app: forgejo
title: Forgejo
version: "14.0.3"
upstream: https://forgejo.org/
languages: [go]
databases: [postgres]
in_catalog: true
report_status: final
last_verified: 2026-07-31
verified_bar: authenticated

variants:
  native: {status: pass}
  nix: {status: pass}
  nix-gen: {status: pass, template: go-source}
---

# Experience Report: Forgejo

Self-hosted Git service (community fork of Gitea).

## What this app exercised

Same shape as Gitea. Showed that a Go binary is named after its module path (`forgejo.org`), independent of the project name.

## What broke

Four defects are shared with Gitea, whose report describes them: an admin bootstrap calling `./forgejo` in a layout where the binary lives in the store, `$out/bin` holding only the generated wrapper, three signing secrets minted by the wrapper and rotating on every restart, and open registration shipping in every Nix variant — with the same fixes, and the same lesson about what the sign-in bar cannot catch.

**What is Forgejo's own is the binary's name.** `buildGoModule` names the output after the module path element, so the source build produces `forgejo.org` (as Miniflux's produces `miniflux.app`), and every `forgejo …` invocation in the recipe had to be `forgejo.org …`.

## What the platform gained

Nothing beyond what Gitea contributed; the two share their defects and their fixes.

## Deployment variants

**Nix (hand-crafted)** takes nixpkgs' `forgejo`, whose `generic.nix` renames the server binary to `gitea` in preInstall; **Nix (template-generated)** compiles from source with `go-source`, and `buildGoModule` names it after the module path element, `forgejo.org`. One application, two Nix packagings, two different binaries.

## Verification

`apps/forgejo/check.py` signs in with the `[probe]` account, which Hop3 owns and rotates, reaches a page only a session can, and confirms a wrong password is refused.

## Reproduce

```bash
hop3 catalog install forgejo
hop3 app check --app forgejo
```

## Open

Nothing open.

## Screenshots

![Sign-in page](images/forgejo-01-login.png) ![After signing in](images/forgejo-02-signed-in.png)
