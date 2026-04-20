# Focalboard (all four variants) — deferred

**Status:** dropped 2026-04-18 for **business reasons, not platform reasons**. **Classification:** upstream blocker (see `local-notes/stacks-and-apps/DEFERRED-APPS.md` → "Upstream blockers").

## Why dropped

- **Upstream archived.** Mattermost shut down the Focalboard project in April 2023. No new releases, no security patches, no community fork with meaningful traction.
- **Absent from nixpkgs.** `builtins.hasAttr "focalboard" nixpkgs` → `false` (checked 2026-04-18), which forces the Nix variants to use a non-reproducible tarball download from upstream releases (`github.com/mattermost-community/focalboard/releases/.../focalboard-server-linux-amd64.tar.gz`, x86_64-linux only).
- **Three-year-old last release.** v7.10.5 (April 2023) — has known CVEs in its Node / Go dependencies with no upstream response.

## This is NOT a platform-limitation record

Hop3 *can* package Focalboard — we did, and the four variants worked at some point. The code moved here not because the platform failed to express what Focalboard needed, but because keeping Focalboard in the "supported" app list is a liability we no longer want (users would assume it's maintained).

If a well-maintained Focalboard fork emerges, packaging it should be mostly mechanical (replace the upstream release URL and SHA256, retest).

## Variants moved

- `apps/real-apps-native/focalboard/` → `apps/bad/real-apps-native-bad/focalboard/`
- `apps/real-apps-docker/focalboard/` → `apps/bad/real-apps-docker-bad/focalboard/`
- `apps/real-apps-nix/focalboard/` → `apps/bad/real-apps-nix-bad/focalboard/`
- `apps/real-apps-nix-gen/focalboard/` → `apps/bad/real-apps-nix-bad/focalboard-gen/` (prebuilt-archive template)
