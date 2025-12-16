# Feature Parity: hop3-cli vs hop3-tui

This document compares the features available in hop3-cli and hop3-tui to identify gaps and plan future development.

## Features in BOTH

| Feature | CLI Command | TUI Screen/Action |
|---------|-------------|-------------------|
| List apps | `apps` | Apps screen |
| App details | `app:status` | App Detail screen |
| Start/Stop/Restart app | `app:start/stop/restart` | Apps & Detail screens |
| Delete app | `app:destroy` | Apps screen (D key) |
| Create app | `app:create` | Apps screen (n key) |
| Deploy from git | `app:launch` | Apps screen (New App dialog) |
| App logs | `app:logs` | Logs screen |
| Env vars list | `config:show` | Env Vars screen |
| Set env var | `config:set` | Env Vars screen (a/e keys) |
| Delete env var | `config:unset` | Env Vars screen (d key) |
| List backups | `backup:list` | Backups screen |
| Create backup | `backup:create` | Backups screen (n key) |
| Restore backup | `backup:restore` | Backups screen (r key) |
| Delete backup | `backup:delete` | Backups screen (d key) |
| List addons | `addons:list` | Addons screen |
| Create addon | `addons:create` | Addons screen (n key) |
| Attach addon | `addons:attach` | Addons screen (a key) |
| Detach addon | `addons:detach` | Addons screen (d key) |
| Delete addon | `addons:destroy` | Addons screen (D key) |
| System status | `system:status` | System screen |
| System info | `system:info` | System screen (info panel) |
| System logs | `system:logs` | System Logs screen |
| Process list | `system:ps` | Processes screen |

---

## Missing from TUI (available in CLI)

### High Priority

| Feature | CLI Command | Description |
|---------|-------------|-------------|
| Deploy from local directory | `deploy <app> [dir]` | Upload local source as tar.gz archive. This is the CLI's primary deployment method. |
| Run command in app | `run <app> <cmd>` | Execute command in app environment. Essential for migrations, shells, one-off tasks. |

### Medium Priority

| Feature | CLI Command | Description |
|---------|-------------|-------------|
| App health check | `app:ping [path]` | HTTP health check to verify app is responding |
| Build logs | `app:build-logs` | View Docker/local build output |
| Process scaling | `ps:scale <proc> <count>` | Scale worker processes |
| Admin: Add user | `admin:user:add` | Create new user account |
| Admin: Remove user | `admin:user:remove` | Delete user account |
| Admin: List users | `admin:user:list` | List all users |
| Admin: Enable/Disable user | `admin:user:enable/disable` | Activate/deactivate accounts |
| Admin: Grant/Revoke admin | `admin:user:grant-admin/revoke-admin` | Manage admin privileges |
| Admin: Set password | `admin:user:set-password` | Change user password |
| Admin: User info | `admin:user:info` | Get user details |
| Admin: Generate token | `admin:user:generate-token` | Generate API token for user |
| Auth: Login | `auth:login` | Interactive login (TUI uses config file) |
| Auth: Logout | `auth:logout` | Revoke current token |
| Auth: Who am I | `auth:whoami` | Show current authenticated user |
| Auth: Register | `auth:register` | Register new user account |

### Low Priority

| Feature | CLI Command | Description |
|---------|-------------|-------------|
| Runtime config | `config:live` | View currently active configuration from running process |
| Config migrate | `config:migrate` | Migrate configuration |
| Plugins list | `plugins` | List loaded server plugins |
| SBOM | `sbom` | Software Bill of Materials |
| PostgreSQL management | `pg` | PostgreSQL-specific operations (placeholder in CLI) |
| Redis management | `redis` | Redis-specific operations (placeholder in CLI) |

---

## TUI-only Features (not in CLI)

| Feature | Description |
|---------|-------------|
| Visual dashboard | Real-time resource monitoring with progress bars and color-coded status |
| Streaming logs | Live log streaming with pause/resume capability |
| Log filtering | Real-time filter while viewing logs |
| Log download | Save logs to local file (~/Downloads or current directory) |
| Sensitive value hiding | Auto-detect and hide secrets (API keys, passwords, tokens) in env vars |
| Visual confirmations | Dialog boxes for destructive actions with explicit confirmation |
| Auto-refresh | Configurable automatic data refresh (default: 5 seconds) |
| Tab completion | Command suggestions in chat interface |
| Keyboard navigation | Full keyboard-driven interface with consistent bindings |
| Color-coded status | Visual indicators for app state (running=green, stopped=dim, failed=red) |
| Resource graphs | CPU, memory, disk usage visualization |

---

## Implementation Plan

### Phase 1: Essential Operations
1. **Local directory deploy** - Match CLI's main deployment workflow
2. **Run command** - Enable migrations, shell access, one-off tasks

### Phase 2: Monitoring & Debugging
1. **App health check (ping)** - Quick health verification
2. **Build logs** - Debug deployment issues
3. **Process scaling** - Adjust worker counts

### Phase 3: Administration
1. **Admin screen** - Full user management interface
   - User list with status
   - Create/delete users
   - Enable/disable accounts
   - Grant/revoke admin
   - Password reset
   - Token generation

### Phase 4: Authentication
1. **Login screen** - Interactive authentication
2. **Session management** - Logout, token display
3. **User profile** - Show current user info (whoami)

---

## Notes

- The CLI supports SSH tunneling for secure remote connections; TUI uses direct HTTP with bearer tokens
- CLI has `--json` output mode; TUI is inherently visual
- CLI has `-y/--yes` flag to skip confirmations; TUI always shows confirmation dialogs for safety
- TUI reads CLI config as fallback for server connection settings:
  - macOS: `~/Library/Application Support/hop3-cli/config.toml`
  - Windows: `%APPDATA%/hop3-cli/config.toml`
  - Linux: `~/.config/hop3-cli/config.toml` or `~/.hop3-cli/config.toml`
- Config priority (highest to lowest):
  1. Environment variables (`HOP3_SERVER_URL`, `HOP3_AUTH_TOKEN`, etc.)
  2. TUI config file (`~/.config/hop3/tui.toml`)
  3. CLI config file (platform-specific paths above)
  4. Default values
