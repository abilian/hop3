# Deployment Architecture

## Overview

Hop3 supports two deployment methods that both use the same unified deployment engine:

1. **Tarball Upload** (Primary) - `hop3 deploy <app>`
2. **Git Push** (Alternative) - `git push hop3 master`

## Unified Deployment Flow

Both deployment methods converge at the same deployment engine (`do_deploy()` in `hop3.deployers.deployer`):

```
┌─────────────────────┐         ┌──────────────────────┐
│  Tarball Upload     │         │    Git Push          │
│  (hop3 deploy)      │         │  (git push hop3)     │
└──────────┬──────────┘         └──────────┬───────────┘
           │                               │
           v                               v
    ┌──────────────┐              ┌─────────────────┐
    │ DeployCmd    │              │  GitHookCmd     │
    │  (RPC)       │              │ (post-receive)  │
    └──────┬───────┘              └────────┬────────┘
           │                               │
           │  1. Extract to               │  1. Extract commit
           │     app.src_path              │     to app.src_path
           │                               │
           └───────────┬───────────────────┘
                       │
                       v
              ┌────────────────┐
              │   do_deploy()  │
              │                │
              │ 1. Load config │
              │ 2. Build       │
              │ 3. Deploy      │
              └────────────────┘
```

## Deployment Method Details

### 1. Tarball Upload (`hop3 deploy`)

**Client-side** (`hop3-cli`):
1. Creates tarball from local directory (respecting `.gitignore`)
2. Base64-encodes the archive
3. Sends via RPC to server

**Server-side** (`DeployCmd`):
1. Receives base64-encoded archive via RPC
2. Decodes and validates archive (security checks)
3. Extracts to `app.src_path` using `extract_archive_to_dir()`
4. Calls `do_deploy(app)`

**Security measures**:
- Archive size limit: 500 MB
- Decompression bomb protection: 2 GB max extracted
- File count limit: 10,000 files max
- Path traversal prevention
- Malicious filename detection

### 2. Git Push (`git push hop3 master`)

**Git hook setup**:
- Post-receive hook installed in bare repository
- Hook script: `cat | HOP3_ROOT="..." hop3-server git-hook <app_name>`

**Server-side** (`GitHookCmd`):
1. Receives push data from stdin: `<old-sha> <new-sha> <ref-name>`
2. Extracts commit using `git archive` to temporary tarball
3. Extracts tarball to `app.src_path`
4. Calls `do_deploy(app)`

**Advantages**:
- Familiar git workflow
- No client-side archive creation needed
- Automatic deployment on push

## Unified Deployment Engine

The `do_deploy()` function in `hop3.deployers.deployer`:

1. **Load Configuration**: Reads `hop3.toml` (or Procfile) from `app.src_path`
2. **Build**: Selects appropriate build strategy (Python, Node.js, Go, etc.)
3. **Deploy**: Selects appropriate deployment strategy (uWSGI, Docker, etc.)
4. **Start**: Launches application workers

Both deployment paths provide identical results - the only difference is how the source code arrives at `app.src_path`.

## Source Types

The deployment engine supports a `source_type` concept for future extensibility:

- `upload`: Tarball uploaded via RPC
- `git`: Deployed via git push
- `marketplace`: (Future) Deployed from marketplace

This allows for different handling or logging based on deployment source.

## Configuration

### Git Push Deployment
Requires bare git repository setup:
```bash
hop3 setup:git <app_name>
```

### Tarball Deployment
No special setup required - works out of the box.

## Testing

Both deployment paths should be tested to ensure consistency:

```bash
# Test tarball deployment
hop3 deploy <app_name>

# Test git push deployment
git remote add hop3 hop3@server:app-name
git push hop3 master
```

## Security Considerations

1. **Archive Validation**: All archives (tarball or git) undergo security validation
2. **Authentication**: Both methods require authenticated RPC access
3. **Size Limits**: Archives are limited to prevent resource exhaustion
4. **Path Traversal**: All extracted files are validated to prevent directory traversal

## Future Enhancements

- **Marketplace Deployment**: Deploy from curated application marketplace
- **Container Deployment**: Direct container image deployment
- **Source URLs**: Deploy from public Git URLs without pushing
