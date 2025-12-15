# TUI Examples Analysis

This document analyzes two Textual-based TUI applications that serve as references for the hop3-tui implementation.

## 1. Mistral-Vibe (AI Chat CLI)

**Location:** `sandbox/mistral-vibe` (symlink to `/Users/fermigier/ghq/github.com/mistralai/mistral-vibe`)

### Overview

A sophisticated chat interface for an AI coding assistant. This is a complex application (~1135 lines in main app.py) with advanced features like streaming, tool approval flows, and dynamic UI switching.

### Architecture Patterns

#### Modal/Mode-Based UI Switching

```python
class BottomApp(Enum):
    Input = "input"
    Config = "config"
    Approval = "approval"

# Dynamic component swapping
def _switch_to_config_app(self):
    self.query_one("#bottom-app-container").remove_children()
    self.query_one("#bottom-app-container").mount(ConfigApp(...))
```

This pattern allows different "sub-applications" to occupy the same screen space, useful for:
- Chat input mode
- Configuration panels
- Approval dialogs for tool execution

#### Compose Method Pattern

```python
def compose(self) -> ComposeResult:
    with VerticalScroll(id="chat"):
        yield WelcomeBanner(self.config)
        yield Static(id="messages")
    with Horizontal(id="loading-area"):
        yield Static(id="loading-area-content")
        yield ModeIndicator(auto_approve=self.auto_approve)
    yield Static(id="todo-area")
    with Static(id="bottom-app-container"):
        yield ChatInputContainer(...)
    with Horizontal(id="bottom-bar"):
        yield PathDisplay(...)
        yield Static(id="spacer")
        yield ContextProgress()
```

Key points:
- Hierarchical widget composition
- Context managers for container nesting
- Named IDs for CSS targeting and programmatic access

#### Asynchronous Event Handling

```python
class EventHandler:
    async def handle_event(self, event: Event) -> None:
        if isinstance(event, ToolCallEvent):
            await self._handle_tool_call(event)
        elif isinstance(event, ToolResultEvent):
            await self._handle_tool_result(event)
        elif isinstance(event, AssistantEvent):
            await self._handle_assistant_message(event)
```

Pattern for handling different event types from an async backend.

#### Streaming Content Updates

```python
class AssistantMessage(Static):
    def append_content(self, content: str) -> None:
        self.markdown_stream.append(content)

    def stop_stream(self) -> None:
        self.markdown_stream.stop()
```

Real-time content updates for streaming responses.

### Custom Widgets

| Widget | Purpose |
|--------|---------|
| `UserMessage` | Display user chat messages |
| `AssistantMessage` | Display AI responses with streaming support |
| `BashOutputMessage` | Display command execution results |
| `ErrorMessage` | Display error states |
| `ChatInputContainer` | Multi-line input with completion |
| `ModeIndicator` | Show current mode (auto-approve, etc.) |
| `PathDisplay` | Show current working directory |
| `ContextProgress` | Token/context usage indicator |
| `ApprovalApp` | Tool execution approval dialog |
| `ConfigApp` | Configuration panel |

### Keyboard Bindings

```python
BINDINGS = [
    Binding("ctrl+c", "force_quit", "Quit", show=False),
    Binding("escape", "interrupt", "Interrupt", show=False, priority=True),
    Binding("ctrl+o", "toggle_tool", "Toggle Tool", show=False),
    Binding("ctrl+t", "toggle_todo", "Toggle Todo", show=False),
    Binding("shift+tab", "cycle_mode", "Cycle Mode", show=False, priority=True),
]
```

### CSS Styling

Single comprehensive CSS file (683 lines) with:
- Theme-aware variables (`$primary`, `$success`, `$error`, `$warning`)
- Layout using grid and flexbox
- Message styling by type (user, assistant, error, tool)
- Collapsible sections for tool output
- Markdown rendering customization

### Key Takeaways for Hop3

**Useful patterns:**
- Modal switching for different contexts (app detail, logs, env vars)
- Streaming for real-time log viewing
- Approval dialogs for destructive operations (stop, destroy)
- Status indicators and progress display

**Complexity to avoid initially:**
- Heavy async event system (overkill for API calls)
- Complex streaming infrastructure


## 2. Textual-System-Monitor (Dashboard)

**Location:** `sandbox/textual-system-monitor` (symlink to external repo)

### Overview

A lightweight system metrics dashboard (~47 lines in main app.py). Clean, simple architecture focused on real-time data display.

### Architecture Patterns

#### Screen-Based Navigation

```python
class Monitor(App[str]):
    MODES = {
        "main": MainScreen,
        "guide": GuideScreen,
        "processes": ProcessesScreen,
        "network": NetworkScreen,
        "cpu": CPU_Screen,
        "drive": DriveScreen,
        "mem": MemoryScreen,
        "gpu": GPU_Screen,
    }
```

Each "mode" is a complete screen. Navigation is simple:
```python
self.switch_mode("cpu")  # Switch to CPU detail screen
```

#### Reactive Data Binding

```python
class Processes(Static):
    processes = reactive([])

    def watch_processes(self, procs: list) -> None:
        # Automatically called when processes changes
        self.update_display(procs)
```

Textual's reactive system automatically triggers UI updates when data changes.

#### Periodic Updates with set_interval

```python
def on_mount(self) -> None:
    self.update_interval = self.set_interval(
        REFRESH_INTERVAL,
        self.update_data
    )
```

Simple polling pattern for real-time updates.

#### Grid Layout for Dashboards

```python
def compose(self) -> ComposeResult:
    yield Header(show_clock=True)
    with Container(id="app-grid"):
        yield Processes(id="processes")
        yield Stats(id="stats")
    yield Footer()
```

### Pane Components

| Pane | Purpose |
|------|---------|
| `Processes` | Top CPU-consuming processes |
| `CPU` | Per-core CPU utilization |
| `Memory` | RAM usage with visual bar |
| `Network` | Network interface statistics |
| `Drives` | Disk space usage |
| `GPU` | GPU statistics |
| `Stats` | General system info |

### CSS Organization

Separate CSS files per screen:
```
src/styles/
├── main_css.tcss
├── cpu_css.tcss
├── drive_css.tcss
├── gpu_css.tcss
├── guide_css.tcss
├── mem_css.tcss
├── network_css.tcss
└── processes_css.tcss
```

Example grid styling:
```tcss
#app-grid {
    layout: grid;
    grid-size: 2;
    grid-columns: 1fr;
    grid-rows: 1fr;
}

#processes {
    row-span: 2;
    background: $panel;
    border: $secondary;
    border-title-align: center;
}
```

### Click-to-Navigate Pattern

```python
class Processes(Static):
    def on_click(self) -> None:
        self.app.switch_mode("processes")
```

Panes are clickable to drill down into detail screens.

### Key Takeaways for Hop3

**Useful patterns:**
- Screen-based navigation (perfect for app list → app detail → logs)
- Grid layout for dashboard overview
- Click-to-drill-down interaction
- Separate CSS files for maintainability
- Periodic refresh for status updates
- Simple reactive data binding

**Limitations:**
- No input handling beyond clicks and keys
- No modal dialogs
- No streaming (just polling)


## Comparison Summary

| Aspect | Mistral-Vibe | System Monitor | Hop3-TUI Recommendation |
|--------|--------------|----------------|------------------------|
| **Lines of code** | ~1135 (app.py) | ~47 (app.py) | Start simple, grow as needed |
| **Navigation** | Modal swapping | Screen modes | **Screen modes** for main nav |
| **Data updates** | Event-driven streaming | Polling | Both (polling + streaming for logs) |
| **CSS organization** | Single file | Per-screen | **Per-screen** files |
| **Input handling** | Complex chat input | Minimal | Medium (commands, forms) |
| **Custom widgets** | Many | Few | Start with few, add as needed |
| **Async complexity** | High | Low | Keep low initially |

## Recommended Hybrid Approach for Hop3-TUI

1. **Base structure:** Screen-based navigation like System Monitor
2. **Dashboard:** Grid layout with clickable panes for quick stats
3. **Detail views:** Separate screens for apps, addons, backups
4. **Modals:** Borrow modal pattern from Mistral-Vibe for confirmations
5. **Chat interface:** Simplified version of Mistral-Vibe's chat input
6. **Streaming:** Use for log viewing (simpler than full chat streaming)
7. **CSS:** Per-screen files for maintainability
8. **Reactive:** Use for status updates and data refresh
