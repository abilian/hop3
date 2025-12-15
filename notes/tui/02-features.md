# Hop3-TUI Features Specification

This document outlines the features for the hop3-tui package.

## Core Design Principles

1. **Screen-based navigation** - Different screens for different contexts
2. **Drill-down capability** - From overview to detail to sub-detail
3. **Keyboard-first** - Full keyboard navigation with mouse as optional
4. **Real-time updates** - Live status for running applications
5. **Chat interface** - Command input with conversational feel
6. **Consistent with Web UI** - Same features, terminal-optimized UX


## Navigation Structure

```
Main Dashboard
├── Apps List Screen
│   └── App Detail Screen
│       ├── Logs View
│       ├── Env Vars View
│       ├── Addons View
│       └── Backups View
├── Addons List Screen
│   └── Addon Detail Screen
├── Backups List Screen
│   └── Backup Detail Screen
├── System Screen
│   ├── Status
│   ├── Processes
│   └── System Logs
├── Users Screen (admin)
│   └── User Detail Screen
└── Chat/Command Screen
```


## Screen Specifications

### 1. Main Dashboard

**Purpose:** Quick overview of server status and recent activity

**Layout (2-column grid):**
```
┌─────────────────────────────────────────────────────────────┐
│ HOP3 Server Dashboard                           user@server │
├────────────────────────────────┬────────────────────────────┤
│ APPLICATIONS          [a]      │ SYSTEM STATUS        [s]   │
│ ───────────────────────────    │ ────────────────────────   │
│ Running: 5                     │ CPU:    ████░░░░░░ 42%     │
│ Stopped: 2                     │ Memory: ██████░░░░ 63%     │
│ Failed:  1                     │ Disk:   ████████░░ 81%     │
│                                │ Uptime: 14d 3h 22m         │
├────────────────────────────────┼────────────────────────────┤
│ RECENT ACTIVITY        [r]     │ QUICK ACTIONS        [q]   │
│ ───────────────────────────    │ ────────────────────────   │
│ 10:32 myapp deployed           │ [d] Deploy new app         │
│ 10:15 api-server restarted     │ [b] Create backup          │
│ 09:45 worker stopped           │ [l] View system logs       │
│ 09:30 backup created           │ [c] Open chat              │
└────────────────────────────────┴────────────────────────────┘
│ [a]pps [s]ystem [b]ackups [o]addons [u]sers [c]hat [?]help  │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Click or press key to navigate to section
- Auto-refresh every 5 seconds
- Recent activity from logs/events

### 2. Apps List Screen

**Purpose:** List all applications with filtering and actions

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Applications                                    Filter: [___]│
├─────────────────────────────────────────────────────────────┤
│ NAME             STATUS     PORT    RUNTIME      UPDATED    │
│ ─────────────────────────────────────────────────────────── │
│ > myapp          RUNNING    8000    uwsgi       2h ago      │
│   api-server     RUNNING    8001    uwsgi       1d ago      │
│   worker         STOPPED    -       uwsgi       3d ago      │
│   frontend       RUNNING    8002    static      5d ago      │
│   broken-app     FAILED     -       uwsgi       1h ago      │
│                                                             │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [Enter] View  [s]tart  [S]top  [r]estart  [d]eploy  [n]ew   │
│ [/] Filter    [←] Back                                      │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Sortable columns (click header or keyboard shortcut)
- Filter by name or status
- Status colors: green=running, gray=stopped, red=failed, yellow=starting/stopping
- Keyboard navigation with j/k or arrows
- Quick actions without entering detail view

### 3. App Detail Screen

**Purpose:** Detailed view of a single application

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ App: myapp                                         RUNNING  │
├─────────────────────────────────────────────────────────────┤
│ INFORMATION                    │ ACTIONS                    │
│ ─────────────────────────────  │ ──────────────────────     │
│ Runtime:    uwsgi              │ [s] Stop                   │
│ Port:       8000               │ [r] Restart                │
│ Hostname:   myapp.example.com  │ [d] Deploy                 │
│ Workers:    2                  │ [b] Backup                 │
│ Created:    2024-01-15         │ [D] Destroy                │
│ Updated:    2024-03-10         │                            │
│                                │                            │
├────────────────────────────────┴────────────────────────────┤
│ RELATED                                                     │
│ ─────────────────────────────────────────────────────────── │
│ [l] Logs (live)     [e] Env Vars (5)    [a] Addons (2)      │
│ [B] Backups (3)     [c] Config                              │
├─────────────────────────────────────────────────────────────┤
│ RECENT LOGS                                                 │
│ ─────────────────────────────────────────────────────────── │
│ 10:32:15 [INFO] Request processed in 45ms                   │
│ 10:32:14 [INFO] GET /api/users 200                          │
│ 10:32:10 [INFO] Database query completed                    │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Real-time status updates
- Quick action buttons
- Recent logs preview (last 5 lines)
- Navigation to related views
- Confirmation dialog for destructive actions (Stop, Destroy)

### 4. Logs View

**Purpose:** Real-time log streaming with search

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Logs: myapp                      [pause] [download] [clear] │
├─────────────────────────────────────────────────────────────┤
│ 10:32:15.123 [INFO]  Request processed in 45ms              │
│ 10:32:14.987 [INFO]  GET /api/users 200                     │
│ 10:32:14.542 [DEBUG] Cache hit for user:123                 │
│ 10:32:10.234 [INFO]  Database query completed               │
│ 10:32:09.876 [WARN]  Slow query detected (>100ms)           │
│ 10:32:05.432 [INFO]  New connection from 10.0.0.5           │
│ 10:32:01.111 [ERROR] Failed to connect to redis             │
│                                                             │
│ ▼ Auto-scrolling                                            │
├─────────────────────────────────────────────────────────────┤
│ Filter: [____________]  Level: [ALL▼]  [←] Back             │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Real-time streaming (SSE-based)
- Pause/resume streaming
- Filter by text pattern
- Filter by log level
- Color-coded log levels
- Download full logs
- Auto-scroll with manual override

### 5. Env Vars View

**Purpose:** View and manage environment variables

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Environment Variables: myapp                                │
├─────────────────────────────────────────────────────────────┤
│ USER VARIABLES (3)                                          │
│ ─────────────────────────────────────────────────────────── │
│ > DEBUG              = false                                │
│   API_KEY            = ****hidden****          [show]       │
│   MAX_WORKERS        = 4                                    │
│                                                             │
│ SERVICE VARIABLES (5)                     [toggle display]  │
│ ─────────────────────────────────────────────────────────── │
│   DATABASE_URL       = postgres://...                       │
│   REDIS_URL          = redis://...                          │
│   ...                                                       │
├─────────────────────────────────────────────────────────────┤
│ [a]dd  [e]dit  [d]elete  [←] Back                          │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Separate user vars from service-generated vars
- Hide/show sensitive values
- Add/edit/delete user variables
- Validation on edit

### 6. Chat/Command Screen

**Purpose:** Conversational interface for complex operations

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Hop3 Command Interface                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ > deploy myapp from github.com/user/repo                    │
│                                                             │
│ Deploying myapp...                                          │
│ ├─ Cloning repository...                    done            │
│ ├─ Detecting runtime...                     Python 3.11     │
│ ├─ Installing dependencies...               done            │
│ ├─ Running migrations...                    done            │
│ └─ Starting application...                  done            │
│                                                             │
│ ✓ myapp deployed successfully on port 8000                  │
│   URL: https://myapp.example.com                            │
│                                                             │
│ > status myapp                                              │
│                                                             │
│ myapp is RUNNING                                            │
│ ├─ Port: 8000                                               │
│ ├─ Workers: 2                                               │
│ └─ Uptime: 5 minutes                                        │
│                                                             │
│ > _                                                         │
├─────────────────────────────────────────────────────────────┤
│ Type command or ? for help                       [←] Back   │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Command history (up/down arrows)
- Tab completion for commands and app names
- Streaming output for long operations
- Progress indicators for deployments
- Rich formatted output
- Help system with `?` or `help`

**Available Commands:**
```
apps                    - List all applications
app <name>              - Show app details
deploy <name> <url>     - Deploy from git URL
start <name>            - Start application
stop <name>             - Stop application
restart <name>          - Restart application
logs <name>             - Stream logs
env <name>              - Show env vars
env <name> set K=V      - Set env var
backup <name>           - Create backup
restore <backup-id>     - Restore backup
status                  - System status
help                    - Show help
```

### 7. System Screen

**Purpose:** Server-level monitoring and management

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ System Status                                               │
├─────────────────────────────────────────────────────────────┤
│ RESOURCES                      │ SERVICES                   │
│ ─────────────────────────────  │ ──────────────────────     │
│ CPU:    ████░░░░░░ 42%         │ nginx       RUNNING        │
│ Memory: ██████░░░░ 63%         │ supervisor  RUNNING        │
│ Swap:   ██░░░░░░░░ 18%         │ postgresql  RUNNING        │
│ Disk:   ████████░░ 81%         │ redis       RUNNING        │
│                                │                            │
│ NETWORK                        │ INFO                       │
│ ─────────────────────────────  │ ──────────────────────     │
│ eth0: ↓ 1.2 MB/s  ↑ 0.8 MB/s   │ Hostname: hop3.local       │
│ Connections: 42                │ Hop3: v0.5.0               │
│                                │ Uptime: 14d 3h 22m         │
├────────────────────────────────┴────────────────────────────┤
│ [p] Processes  [l] System Logs  [c] Config  [←] Back        │
└─────────────────────────────────────────────────────────────┘
```

### 8. Addons List/Detail Screens

**Purpose:** Manage addon services (PostgreSQL, Redis, S3, etc.)

**Features:**
- List all addons with type and associated app
- Create new addon instances
- Attach/detach addons to/from apps
- View connection details
- Destroy addons (with confirmation)

### 9. Backups List/Detail Screens

**Purpose:** Manage application backups

**Features:**
- List all backups with size, date, app
- Create new backup
- View backup details (manifest, checksums)
- Restore backup (with confirmation)
- Delete backup (with confirmation)

### 10. Users Screen (Admin Only)

**Purpose:** User management for administrators

**Features:**
- List all users
- Add new user
- Enable/disable users
- Grant/revoke admin role
- Generate API tokens
- Reset passwords


## Interaction Patterns

### Keyboard Shortcuts (Global)

| Key | Action |
|-----|--------|
| `?` or `F1` | Help overlay |
| `q` or `Esc` | Back / Quit |
| `Ctrl+C` | Force quit |
| `:` | Open command input |
| `/` | Search/filter |
| `Tab` | Next pane |
| `Shift+Tab` | Previous pane |
| `j` / `k` | Navigate down/up |
| `Enter` | Select / Confirm |
| `r` | Refresh current view |

### List Navigation

| Key | Action |
|-----|--------|
| `j` / `↓` | Next item |
| `k` / `↑` | Previous item |
| `g` / `Home` | First item |
| `G` / `End` | Last item |
| `Enter` | Open detail |
| `/` | Filter |

### Confirmation Dialogs

For destructive actions (stop, destroy, delete):
```
┌──────────────────────────────────────┐
│ Confirm Stop                         │
├──────────────────────────────────────┤
│ Are you sure you want to stop myapp? │
│                                      │
│ This will terminate all processes.   │
│                                      │
│        [Yes, Stop]  [Cancel]         │
└──────────────────────────────────────┘
```

### Toast Notifications

For non-blocking feedback:
```
┌─────────────────────────────────────┐
│ ✓ myapp restarted successfully      │
└─────────────────────────────────────┘
```


## Technical Requirements

### API Integration

- Use existing JSON-RPC API (`POST /rpc`)
- Support both session auth and token auth
- Handle async operations with polling
- Streaming for logs via SSE

### Data Refresh Strategy

| View | Refresh Strategy |
|------|------------------|
| Dashboard | Auto-refresh every 5s |
| Apps List | Auto-refresh every 10s |
| App Detail | Auto-refresh every 3s (if transitional state) |
| Logs | Real-time streaming |
| Env Vars | Manual refresh |
| System | Auto-refresh every 5s |

### Configuration

```toml
# ~/.config/hop3/tui.toml
[server]
url = "https://hop3.example.com"
# or
ssh_host = "hop3.example.com"

[display]
theme = "dark"  # dark, light, auto
refresh_interval = 5
show_clock = true

[shortcuts]
# Custom key bindings
```

### Error Handling

- Connection errors: Show reconnection dialog
- Auth errors: Redirect to login
- API errors: Show toast with error message
- Network timeout: Show retry option


## Implementation Status

### Phase 1 Features (MVP) - IMPLEMENTED

| Feature | Status | Notes |
|---------|--------|-------|
| Dashboard overview | Done | 2x2 grid with apps summary, system status, activity, quick actions |
| Apps list with filtering | Done | DataTable with filter input, keyboard navigation |
| App start/stop/restart | Done | Via keyboard shortcuts and action buttons |
| App detail view | Done | Info panel, actions panel, logs preview |
| Logs view (streaming) | Done | Simulated streaming, filter, pause/resume |
| Command interface | Done | 10+ commands implemented |
| System status | Done | CPU, memory, disk with progress bars |
| Configuration | Done | TOML file + environment variables |
| Tests | Done | 125 tests, 82% coverage |

### Phase 2 Features - TODO

| Feature | Status | Notes |
|---------|--------|-------|
| Env vars management | Not started | View/edit environment variables |
| Addons management | Not started | List/attach/detach addons |
| Backups management | Not started | Create/restore/delete backups |
| Command completion | Not started | Tab completion for commands and app names |
| User management | Not started | Admin-only user management |

### Phase 3 Features - TODO

| Feature | Status | Notes |
|---------|--------|-------|
| Deployment wizard | Not started | Step-by-step deployment flow |
| Configuration editor | Not started | Edit hop3.toml in TUI |
| Multi-server support | Not started | Switch between servers |
| Custom themes | Not started | User-defined color schemes |
| Plugin system | Not started | Extensions for custom screens/commands |


## Dependencies

```toml
[dependencies]
textual = ">=0.50.0"
httpx = ">=0.27.0"  # For async HTTP
rich = ">=13.0.0"   # For rich text (included with textual)
```


## File Structure

```
packages/hop3-tui/
├── pyproject.toml
├── src/
│   └── hop3_tui/
│       ├── __init__.py
│       ├── __main__.py          # Entry point
│       ├── app.py               # Main App class
│       ├── api/
│       │   ├── __init__.py
│       │   ├── client.py        # API client
│       │   └── models.py        # Response models
│       ├── screens/
│       │   ├── __init__.py
│       │   ├── dashboard.py
│       │   ├── apps.py
│       │   ├── app_detail.py
│       │   ├── logs.py
│       │   ├── env_vars.py
│       │   ├── system.py
│       │   ├── chat.py
│       │   └── ...
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── status_badge.py
│       │   ├── progress_bar.py
│       │   ├── confirmation.py
│       │   └── ...
│       ├── styles/
│       │   ├── base.tcss
│       │   ├── dashboard.tcss
│       │   ├── apps.tcss
│       │   └── ...
│       └── config.py            # Configuration handling
└── tests/
    └── ...
```
