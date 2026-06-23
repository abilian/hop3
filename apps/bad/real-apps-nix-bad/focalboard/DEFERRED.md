# Focalboard (nix) — dropped

**Business-reasons drop. Not a platform limitation.** Moved here 2026-06-23.

## Why

Mattermost archived Focalboard in April 2023; it has been unmaintained since
(v7.10.5 is the final release) and is absent from nixpkgs. The app still deploys
and serves correctly across all four variants — we packaged it successfully — but
the business case for advertising an abandoned app has gone.

## Unblocker

If an actively-maintained fork or replacement emerges, re-test the four variants
against the current platform and move back to `apps/real-apps-*/focalboard/`.
