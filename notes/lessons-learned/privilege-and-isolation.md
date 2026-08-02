# Lessons Learned: Privilege Separation & Isolation

**Updated**: 2026-06-17: first cut, from the ADR 046 resource-limits work.

Where privileged effects and security boundaries live, and the patterns that keep them small and auditable. Context: [ADR 046](../adrs/046-declarative-app-resources.md) and the `hop3-rootd` daemon.

## Privileged Operations Live Behind the Daemon, With a Default-Deny Allow-List

When the platform needs a privileged action (cgroup writes, mounts, opening ports), don't run it inline from the unprivileged deploy path "just this once". Put the capability in the privileged daemon (rootd), expose it as a narrow op, and gate it with a *default-deny* allow-list plus a startup reconcile. The unprivileged side only asks; the daemon decides and is the single thing that touches the resource.

**Case (June 2026, ADR 046):** enforcing native `[limits]` needs cgroup v2 writes; volumes need bind/tmpfs mounts, both privileged. The work added rootd `cgroup.*` and `mount.*` op families. `mount.bind` is constrained by a default-deny allow-list; both reconcile their state at startup; the deployer only issues requests.

Principles:

- **Default-deny**: enumerate what's allowed and reject everything else; don't blocklist.
- **Reconcile at startup** so a crash/restart converges to the intended state.
- A growing list of "just run this as root from the deployer" shortcuts *is* a privilege-escalation surface. Resist it; route through a daemon op.

## Confine Path-List Config with `realpath` on Both Sides

When config lets a user list paths that must stay inside a boundary (an app's own directory), a *lexical* check (`os.path.normpath`, prefix-string compare) is not enough. An in-tree symlink pointing outside defeats it. Resolve symlinks with `realpath` on **both** the candidate path and the allowed root, then check containment on the resolved paths.

```python
# BAD - lexical only; a symlink at app/data/link → /etc passes
norm = os.path.normpath(candidate)
if not norm.startswith(app_root):
    reject()

# GOOD - resolve symlinks on both sides, then contain
real = os.path.realpath(candidate)
root = os.path.realpath(app_root)
if os.path.commonpath([real, root]) != root:
    abort_loud(...)
```

**Case (June 2026):** `[backup].paths` lets an app add directories to its backup, with the invariant that a backup can only read data inside the app's own subtree. A lexical containment check passed for `app/data/link` even when `link` → `/etc`. The fix `realpath`'d both sides and added a regression test that *tries* to escape (a symlink to outside the tree) and asserts it fails loudly.

Never trust lexical path arithmetic for a security boundary: symlinks, `..`, and mounts all defeat it. Always add the escape-attempt regression test.