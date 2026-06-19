# Demo 60 — CLI Surface Tour

A breadth-first demo that exercises as much of the `hop3` CLI as possible in a
single run, on one throwaway app. Where the other demos each show **one** feature
deeply, this one is deliberately **wide**.

It deploys a tiny Flask app (`app/`) and then walks the command surface:

1. Client-side + read-only system commands (`version`, `system info/status/logs`,
   `plugin list`, `addon types/list`, `app list`, `cert status`, `aliases`, …)
2. Deploy + inspect (`app status/ping/logs/debug/sbom/run`)
3. Environment variables (`env set/show/get/live/unset`, `--sources`)
4. Domains (`domain add/list/remove/set`)
5. Process scaling (`ps`, `ps scale`)
6. Addon lifecycle for **all four types** (postgres / mysql / redis / s3) via a
   per-type helper: `addon create/show/status/exists/credentials/endpoint/
   query/dump/clone/attach/promote/expose/unexpose/detach/destroy` plus
   type-specific reads (`settings`/`activity`/`locks`/`info`/`flush`) — each
   type is skipped if its service isn't installed
7. Backups (`backup create/list/show/restore/destroy`)
8. App lifecycle (`app restart/stop/start`)
9. A throwaway user-management lifecycle (`user add/show/disable/enable/
   grant-admin/revoke-admin/set-password/generate-token/remove`) — admin only
10. Client-side read-only (`help`, `context list`, `server list`,
    `settings show/get`, `use`, `completion`)

It deliberately does **not** run commands that would disrupt the run itself —
`tunnel` (blocks), `auth login`/`logout`/`login`/`init` (re-auth the connection),
`server`/`context` *mutation*, `app create`/`backup register` (need external
inputs), and addon `export`/`import`/`restore` round-trips. See the script
docstring for the full rationale.

It prints a **coverage summary** at the end (commands exercised, and which exited
non-zero — usually an unavailable feature or empty state). It runs
non-interactively (`HOP3_NO_INPUT`) and is **self-cleaning**: the addon, backup,
throwaway user, and the app are all torn down.

Run it like any other demo:

```bash
python demos/demo.py --host <server> demo60
```
