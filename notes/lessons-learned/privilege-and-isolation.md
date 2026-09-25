# Lessons Learned: Privilege Separation & Isolation

**Updated**: 2026-09-08, adding the `app shell` sections. First cut 2026-06-17, from the ADR 046 resource-limits work.

This note records where privileged effects and security boundaries live, and the patterns that keep them small and auditable. The context is [ADR 046](../adrs/046-declarative-app-resources.md) and the `hop3-rootd` daemon.

## Privileged Operations Live Behind the Daemon, With a Default-Deny Allow-List

When the platform needs a privileged action (cgroup writes, mounts, opening ports), the capability goes in the privileged daemon (rootd), exposed as a narrow op and gated with a *default-deny* allow-list plus a startup reconcile. Running it inline from the unprivileged deploy path "just this once" grows the escalation surface. The unprivileged side only asks; the daemon decides and is the single thing that touches the resource.

**Case (June 2026, ADR 046):** enforcing native `[limits]` needs cgroup v2 writes; volumes need bind/tmpfs mounts, both privileged. The work added rootd `cgroup.*` and `mount.*` op families. `mount.bind` is constrained by a default-deny allow-list, both reconcile their state at startup, and the deployer only issues requests.

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

## A Shell Into an App Is No New Authority

**September 2026, `hop3 app shell`.** The instinct is that an interactive shell is an escalation and wants an admin gate. Against the platform's documented model it is not: any authenticated account can already stop, reconfigure, back up or destroy every app and read every addon credential, and `hop3 run` already executes arbitrary argv as the `hop3` user. A shell changes duration and observability, and the design addresses those two: one log line per session with the key fingerprint, the app and the shell, and no shared history file. It refuses an app that does not exist, was never deployed, or runs under docker-compose, where the alternative would be a prompt in an empty directory. If the operator-equivalent model itself is wrong, the change is larger and moves `app run`, `app destroy` and `env show --show-secrets` together. ADR 061 later made that move: all three need the `deployer` role, and the shell rides the `hop3` SSH key, which carries no account.

## Two Keys, Two Transports

The `hop3` account's authorized key carries a forced command and `no-port-forwarding`: it is the `git push` key, and the same forced command dispatches `app-shell`. It cannot carry the `ssh -L` tunnel the CLI speaks JSON-RPC through. The tunnel and `hop3 login --ssh` connect with the operator's plain key in root's `authorized_keys`; root reaches the server-side commands through `su - hop3 -c`. Both paths end in the same process as the same user; sshd decides what each is allowed on the way in. The e2e image now carries both keys for that reason.
