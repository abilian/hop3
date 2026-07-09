# ADR 037: Git-Based Deployment Architecture

- **Status**: Final
- **Type**: Architecture
- **Created**: 2026-03-05
- **Related-ADRs**: [036](./036-cli-ergonomics.md)

## Context

Hop3 supports Heroku-style `git push` deployments, where developers push code to a git remote on the Hop3 server, triggering automatic deployment. This is a classic PaaS pattern, and it stands alongside the explicit `hop3 deploy` path: the two are alternatives.

Git-based deployment is valuable for:

- A familiar Heroku-style workflow
- CI/CD integration (push to deploy)
- Version control as the deployment trigger
- Deploying without a separate deploy command

A naive implementation runs into an architectural flaw worth recording, because it shaped the decision below. A post-receive hook can be made to call an RPC command:

```bash
cat | HOP3_ROOT="/home/hop3" hop3-server git-hook <app_name>
```

where the RPC command reads push data from stdin, extracts the commit to the source directory, and triggers `do_deploy()`. This fails: the server CLI (`hop3-server`) scans `hop3.server.cli` for commands, not `hop3.commands` (the RPC commands), so `hop3-server git-hook` is an unknown command. The deeper issue is conceptual placement: RPC commands exist for client-server communication, whereas a git hook is an internal server operation. Git hook handling therefore belongs in the server CLI, not among the RPC commands.

## Decision

Git hook handling lives as a dedicated server CLI command (Option A below). The operator workflow is:

```
git push hop3@server:myapp main
   │
   ▼
SSH (forced command in authorized_keys)
   │
   ▼
hop3-server git-receive-pack /home/hop3/apps/myapp/git
   │  ├─ auto-creates the App if it does not exist
   │  ├─ initialises the bare repo (lazy)
   │  └─ runs git-receive-pack
   ▼
post-receive hook  →  hop3-server git-hook myapp
   │
   ▼
parse push data → git archive → extract to src/ → do_deploy()
```

Both `git-receive-pack` and `git-upload-pack` (for clones/fetches) are wired.

### Option A: Server CLI command

Git hook handling is a proper server CLI command:

```
hop3-server/
└── src/hop3/server/cli/
    └── git_hook.py
```

```python
# hop3/server/cli/git_hook.py
@register
class GitHook(Command):
    """Handle git post-receive hook (internal use only)."""

    name = "git-hook"

    def add_arguments(self, parser):
        parser.add_argument("app", type=str, help="App name")

    def run(self, app: str):
        # Read stdin, extract commit, trigger deployment
        ...
```

The command is marked hidden (not user-facing). The previous RPC-command implementation under `hop3/commands/git.py` does not exist; `hop3/core/git.py` creates the post-receive hook that invokes `hop3-server git-hook`.

**Why Option A:**

- Clean separation of concerns: the server CLI handles server operations, RPC handles client-server communication.
- The command is discoverable via `hop3-server --help` (unless hidden), consistent with other server operations.
- It follows the established pattern for server-side operations and is explicit about what `hop3-server` can do.

The trade-off is some code duplication with a hook-script approach, and the command must handle its own DB session creation.

## Alternatives Considered

### Option B: Direct Python script

Replace the bash hook with a Python script that imports deployment functions directly:

```python
#!/usr/bin/env python3
# hooks/post-receive
import sys
from hop3.core.git_deployment import deploy_from_push

app_name = sys.argv[1]
push_data = sys.stdin.read()
deploy_from_push(app_name, push_data)
```

**Pros:** simplest approach, no command abstraction; direct import with no CLI parsing overhead; clearly internal and not user-facing.

**Cons:** the hook must manage the Python environment and path itself, and there is less visibility into what is happening.

### Option C: Use the `local` subcommand

Update the hook to route through the existing `local` command:

```bash
cat | hop3-server local git-hook <app_name>
```

**Pros:** minimal changes; reuses existing infrastructure.

**Cons:** extra indirection (`local` → RPC command); `git-hook` remains in the wrong conceptual location (among RPC commands); the resulting architecture is confusing.

## Consequences

### Positive

- The deployment trigger is part of the version-control workflow developers already use.
- Server operations and client-server RPC are cleanly separated.
- `git push` and `hop3 deploy` coexist as two paths to the same deployment.

### Negative

- Some logic is duplicated relative to a pure hook-script approach.
- The server CLI command must create and manage its own DB session.

## Security Implications

Pushes arrive over SSH and are constrained by a forced command in `authorized_keys`, so an incoming key can only run `git-receive-pack` / `git-upload-pack` against its app's repository rather than an arbitrary shell.

## Unresolved Questions

1. **Multi-branch deployment.** Only the first ref is processed. A future design could configure which branches trigger deployment.

2. **Webhook-based triggers.** GitHub/GitLab webhooks are an alternative to SSH-based `git push`, more familiar for cloud-native workflows, and would require a webhook endpoint in the API.

3. **Deployment failure handling.** A `git push` can succeed while the subsequent deployment fails: the code is already pushed, and the user sees the error in the terminal. This needs clear error messages and a recovery path.

## References

- [ADR 036: CLI Ergonomics](./036-cli-ergonomics.md): hidden commands and the `hop3 deploy` command form
- `hop3/core/git.py`: git repository management and hook creation
