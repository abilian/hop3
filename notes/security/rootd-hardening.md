# hop3-rootd: systemd sandboxing and relocation (open security debt)

**Status:** open. Deferred from 0.5, through 0.6, and out of scope for the
**0.7** cut. The `hop3-rootd` systemd unit ships with **minimal
sandboxing** — a plain `Type=notify` root daemon with socket activation —
matching the proven-working container/supervisor model. This document records
why the heavy hardening was removed, what was empirically established, and the
work needed to redo it properly.

**Why this is still open rather than closed as "won't do":** one of the two
items below is a live privilege-escalation path, not a hardening nicety. The
other is defence in depth. They are recorded together because the same
relocation unblocks both.

**ADRs:** [041](../adrs/041-privileged-operations-agent.md) is the governing
decision (the privileged-operations agent; §10 no hop3→root escalation, §14
distribution/install). Also relevant:
[010](../adrs/010-security-and-resilience.md) (the unprivileged-`hop3` model
this protects), [040](../adrs/040-network-firewall-and-port-exposure.md) and
[045](../adrs/045-fixed-port-registry.md) (the firewall and port operations
rootd executes), [048](../adrs/048-server-config-and-secret-storage.md) (secret
storage and rootd's read access),
[055](../adrs/055-app-runtime-uid-separation.md) (per-app uid separation — the
proposal that makes rootd's `SO_PEERCRED` boundary meaningful), and
[043](../adrs/043-unified-testing-architecture.md) (where the missing test
belongs). Operator-facing summary: [security-model.md](security-model.md).

## Background

`hop3-rootd` is the privileged executor. It runs as root and shells out to
**three** external tools with very different filesystem and capability needs:

- **nft** — firewall rules. Needs `CAP_NET_ADMIN`, `AF_NETLINK`. The original
  hardening was designed around this tool, and minimally.
- **nginx** — `nginx -t` (validate) and `nginx -s reload`. Validation opens
  nginx's `www-data`-owned error log, the pid file and temp dirs, and reads the
  app vhost configs under `/home/hop3/nginx`.
- **systemctl** — `systemctl reload nginx`, which talks to systemd over `/run`.

A systemd unit's sandbox applies to **all child processes**, so hardening
designed for nft also constrains the nginx and systemctl subprocesses.

## What went wrong (established empirically on a real systemd host)

The daemon had **never started on a systemd host** — it crash-looped ~1620
times — so none of the hardening was ever exercised. Once it was fixed enough
to start, the hardening broke the nginx role on three independent axes:

| Directive | Symptom | Cause |
|-----------|---------|-------|
| `ProtectHome=true` | `status=203/EXEC` (daemon never execs) | The venv interpreter `/home/hop3/venv/bin/python3` is under `/home`, which `ProtectHome=true` turns into an empty tmpfs in the unit namespace, so the kernel cannot resolve the interpreter at `execve`. |
| `ProtectSystem=strict` | `nginx -t` → `[emerg] … failed (30: Read-only file system)` on `/run/nginx.pid` (and `/var/log/nginx`) | `strict` makes everything outside `ReadWritePaths` read-only, including `/var/log/nginx`, `/var/lib/nginx` and `/run`. |
| `CapabilityBoundingSet=CAP_NET_ADMIN` (drops `CAP_DAC_OVERRIDE`) | `nginx -t` → `[emerg] … failed (13: Permission denied)` on `/var/log/nginx/error.log` | rootd runs `nginx -t` as root but **without** `CAP_DAC_OVERRIDE`, so it cannot open nginx's `www-data`-owned error log. A DAC failure, not a read-only mount. |
| `ProtectHome=*` (any value) | `nginx -t` validates the *wrong* config | App vhost configs live in `/home/hop3/nginx`, hidden by ProtectHome, so `include /home/hop3/nginx/*.conf` matches nothing. |

Two notes that shaped the fix:

- `nginx -s reload` **works** via `systemctl` even under the sandbox, because
  systemd performs the reload outside the unit's namespace. Only the in-process
  `nginx -t` validation is affected.
- **Test-harness blind spot (since closed).** The system test's HTTP check hit
  the app's *direct port*, not the nginx vhost, so uWSGI apps passed while their
  vhosts never applied. Only the static app, which has no direct port, surfaced
  it. Verification now goes through the vhost hostname, and a green deploy also
  requires the app's own authenticated check to pass.

## The escalation this leaves open (HIGH)

rootd executes its interpreter and code from `/home/hop3/venv`, which is
**owned and writable by the unprivileged `hop3` user**. A compromised `hop3`
can overwrite that code and trigger a restart, giving root RCE with
`CAP_NET_ADMIN`. This is precisely what ADR 041 §10 exists to eliminate; its
reference unit installs to a root-owned `/opt`. `BindReadOnlyPaths` protects
the namespace *view*, not the host source, and does **not** fix it.

Still true as of 0.7: `constants.py` sets `VENV_DIR = /home/hop3/venv`, and
`_resolve_daemon_command` probes that path first. `/opt/hop3/.venv` is listed
as a candidate but is not where the installer puts the daemon.

## The work

### 1. Relocate rootd out of `/home` into a root-owned tree

Fixes the escalation **and** lets `ProtectHome=true` work as written — one
change unblocking both items, which is why it is first.

Target: `/opt/hop3-rootd` with its own venv, `root:root`, not writable by
`hop3`. Touches `install_rootd_package` (install as root into the new venv
rather than via `su - hop3`), the `_resolve_daemon_command` candidate order,
`constants.py`, and the demo/supervisor path (`demos/lib/backends/docker.py`
runs `/home/hop3/venv/bin/hop3-rootd`). Re-validate on systemd **and** in a
container.

### 2. Redesign the sandbox, tested against all three tools

Validated building blocks from the original investigation:

- `ProtectSystem=full` (keeps `/usr` and `/etc` read-only while leaving `/var`
  and `/run` writable for nginx logs, pid and temp files, and for systemd) — or
  `strict` plus explicit `ReadWritePaths=/var/log/nginx /var/lib/nginx /run`.
- For the nginx configs in `/home/hop3/nginx`: relocate them too, or
  `ProtectHome=read-only`, or `ProtectHome=tmpfs` plus
  `BindReadOnlyPaths=/home/hop3/nginx` (ensuring that directory exists before
  the unit starts).
- For `nginx -t`'s DAC problem, prefer **not** granting `CAP_DAC_OVERRIDE`.
  Investigate `nginx -t -e /dev/stderr` so validation never touches the
  `www-data` log — **unverified, must be tested**. Fallback: grant
  `CAP_DAC_OVERRIDE` and document the trade-off.
- Re-add, each re-tested against a real `nginx -t`, a real nft rule and a real
  reload: the kernel-surface protections, `RestrictAddressFamilies`,
  `MemoryDenyWriteExecute`, the seccomp `SystemCallFilter`, and resource limits
  (`MemoryMax` / `TasksMax` / `LimitNOFILE` — the original `16` / `1024` may be
  too tight for the nginx subprocess), `PrivateTmp` / `PrivateDevices` /
  `PrivateMounts`.

### 3. Exercise the sandbox in CI

The `c_e2e` installer suite now starts rootd under the **real systemd unit**
(`test_hop3_rootd_service`), which closes the "never started on systemd" gap
that let this ship broken. What it does *not* yet do is drive a privileged
operation **through rootd under a hardened unit** — because there is no
hardening to exercise. When item 2 lands, that test must perform a real nginx
validate + reload and a real nft rule through the daemon, or the sandbox will
be unverified exactly as before.

## The guard

`test_rootd.py::test_service_template_is_minimal_pending_v06_hardening` fails
if a breaking directive is re-added without this redesign. It is deliberate:
the minimal unit is a decision, not an oversight, and the test makes re-adding
hardening a conscious act. Rename it alongside item 2 — the `v06` in its name
is now three releases stale.

## Resolved since this note was written

- **`HOP3_SECRET_KEY` had two sources.** Superseded by
  [ADR 048](../adrs/048-server-config-and-secret-storage.md) ("one secret, one
  source"), which moves the JWT signing key to `/etc/hop3/secret-key` and
  removes the `/etc/default/hop3` ↔ `hop3-server.toml` split that could silently
  invalidate freshly-minted tokens.
- **The deployer did not upload `hop3-rootd`** (only `hop3-server`). Fixed in
  0.5 (`deployer/deploy.py::_upload_rootd_package`). The cloud test surfaced it
  only because a freshly-rebuilt server has no leftover `/tmp/hop3-rootd`; worth
  remembering for other deploy paths that assume leftovers.

## Not a security item

**demo08 / `110-flask-gunicorn-poetry`** — the Python toolchain still has no
Poetry support: a Poetry-managed `pyproject.toml` without a committed
`requirements.txt` fails with "Poetry is not detected by the Python toolchain".
Either detect Poetry and `poetry export` at package time, or document the
requirement. This is a toolchain gap and belongs in the deferred-apps log, not
in a security note; recorded here only because that is where it was first
written down.
