# ADR 037: Git-Based Deployment Architecture

**Status**: Implemented (via Option A)
**Type**: Architecture
**Created**: 2026-03-05
**Updated**: 2026-04-22
**Related-ADRs**: 036

## Revisions

- v1.3: CLI example migrated to the space form (`hop3 deploy`) per ADR 036 (2026-04-22).
- v1.2: Promoted from Draft to Implemented via Option A (2026-04-14).
- v1.0: Original draft (2026-03-05).

## Implementation Status

Implemented as the recommended Option A from the original draft. The body below describes the original problem and decision context; the resulting operator workflow is:

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

Both `git-receive-pack` and `git-upload-pack` (for clones/fetches) are wired. The `hop3 deploy` path remains available alongside `git push`; they are alternatives, not replacements.

## Context

Hop3 aims to support Heroku-style `git push` deployments where developers push code to a git remote on the Hop3 server, triggering automatic deployment. This is a classic PaaS pattern.

### Current State (Broken)

The current implementation has an architectural flaw:

1. **Git hook script** (`core/git.py:72-80`) creates a post-receive hook that calls:
   ```bash
   cat | HOP3_ROOT="/home/hop3" hop3-server git-hook <app_name>
   ```

2. **GitHookCmd** (`commands/git.py`) is an RPC command that:
   - Reads push data from stdin
   - Extracts the commit to the source directory
   - Triggers `do_deploy()`

3. **Problem**: The server CLI (`hop3-server`) only scans `hop3.server.cli` for commands, NOT `hop3.commands` (RPC commands). So `hop3-server git-hook` fails with "unknown command".

4. **The command is in the wrong place**: RPC commands are for client-server communication. Git hooks are internal server operations.

### Why This Matters (Future)

Git-based deployment is valuable for:
- Familiar Heroku-style workflow
- CI/CD integration (push to deploy)
- Version control as deployment trigger
- No need for separate deploy command

## Decision

When git deployment becomes a priority, implement one of these approaches:

### Option A: Server CLI Command (Recommended)

Move git hook handling to a proper server CLI command:

```
hop3-server/
└── src/hop3/server/cli/
    └── git_hook.py       # New file
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

**Pros:**
- Clean separation: server CLI for server operations, RPC for client-server
- Command is discoverable via `hop3-server --help` (if not hidden)
- Consistent with other server operations

**Cons:**
- Some code duplication with current implementation
- Need to handle DB session creation

### Option B: Direct Python Script

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

**Pros:**
- Simplest approach, no command abstraction needed
- Direct import, no CLI parsing overhead
- Clear that this is internal, not user-facing

**Cons:**
- Need to handle Python environment/path in hook
- Less visibility into what's happening

### Option C: Use `local` Subcommand

Update the hook to use the existing `local` command:

```bash
cat | hop3-server local git-hook <app_name>
```

**Pros:**
- Minimal changes required
- Reuses existing infrastructure

**Cons:**
- Extra indirection (`local` → RPC command)
- `git-hook` still in wrong conceptual location (RPC commands)
- Confusing architecture

## Recommendation

**Option A (Server CLI Command)** is recommended because:

1. It correctly separates concerns (server CLI vs RPC)
2. It's explicit about what `hop3-server` can do
3. It follows the established pattern for server-side operations

## Implementation Plan

When git deployment becomes a priority:

1. Create `hop3/server/cli/git_hook.py` with the deployment logic
2. Mark it as `hidden = True` (not user-facing)
3. Delete `hop3/commands/git.py` (the broken RPC command)
4. Update `core/git.py` hook creation (should work as-is if command name stays `git-hook`)
5. Add integration tests that actually invoke the CLI

## Files Affected

| File | Action |
|------|--------|
| `commands/git.py` | Delete |
| `server/cli/git_hook.py` | Create |
| `core/git.py` | Verify hook script works |
| Tests | Update to test via CLI |

## Open Questions

1. **Should git deployment support multiple branches?**
   - Current: Only processes first ref
   - Future: Configure which branches trigger deployment?

2. **Should we support GitHub/GitLab webhooks instead?**
   - Alternative to SSH-based git push
   - More familiar for cloud-native workflows
   - Would need webhook endpoint in the API

3. **How to handle deployment failures?**
   - Git push succeeds but deployment fails
   - User sees error in terminal but code is already pushed
   - Need clear error messages and recovery path

## Related

- [ADR 036: CLI Ergonomics](./036-cli-ergonomics.md) - Hidden commands
- `hop3/commands/git.py` - Current (broken) implementation
- `hop3/core/git.py` - Git repository management
