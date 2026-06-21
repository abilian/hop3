# ADR 025: CLI User Experience Improvements

**Status**: Final
**Type**: Feature
**Created**: 2025-11-08
**Related-ADRs**: 018, 019, 024, 034, 036

Command syntax uses the space form (`hop3 backup destroy`, `hop3 addon destroy`) rather than the colon form (`hop3 backup:delete`, `hop3 services:destroy`), per [036-cli-ergonomics.md](036-cli-ergonomics.md). Help-text conventions and error-recovery hints are specified in that ADR; streaming output uses the protocol defined in [034-streaming-deployment-logs.md](034-streaming-deployment-logs.md).

## Context

The Hop3 CLI (`hop3` command) is the primary interface for users interacting with the platform. While functional, the current CLI lacks several features that are standard in modern CLI tools:

1. **No confirmation for destructive actions**: Commands like `hop3 app destroy`, `hop3 backup destroy`, and `hop3 addon destroy` permanently delete data without asking for confirmation, creating risk of accidental data loss.

2. **Limited output formatting**: Output is plain text, making it harder to scan information quickly. No visual distinction between different types of messages (errors, warnings, success).

3. **No machine-readable output**: Scripts and automation tools cannot easily parse CLI output, requiring custom parsing or direct API access.

4. **No progress indicators**: Long-running operations (deployments, backups) provide no feedback, leaving users uncertain if the command is still running.

5. **Poor error messages**: Validation errors are generic and don't provide actionable suggestions for fixing problems.

6. **No quiet mode**: Cannot suppress output for scripting scenarios where only exit codes matter.

### User Pain Points

From user feedback and observation:

- **Accidental deletions**: Users have accidentally destroyed apps or deleted backups by running commands in the wrong directory or with wrong arguments
- **Uncertain status**: During deployments, users don't know if the process is stuck or still working
- **Automation difficulties**: Users writing scripts need to parse text output, which is fragile
- **Information overload**: In CI/CD scenarios, verbose output clutters logs
- **Poor discoverability**: Users don't realize they made a mistake until after the command fails

### Design Goals

The CLI improvements should:
- **Prevent accidents**: Confirm destructive actions before executing
- **Improve clarity**: Use colors and formatting to make output scannable
- **Enable automation**: Support machine-readable JSON output
- **Show progress**: Provide feedback for long-running operations
- **Guide users**: Give helpful error messages with suggestions
- **Maintain simplicity**: Default behavior should remain simple and intuitive

## Decision

We will implement a comprehensive set of CLI user experience improvements organized into five categories:

### 1. Interactive Confirmation for Destructive Actions

**Design:**
- Add `destructive: ClassVar[bool]` metadata to the `Command` base class
- Mark commands that delete/destroy data as `destructive = True`
- CLI automatically prompts for confirmation before executing destructive commands
- Users can bypass prompts with `-y` / `--yes` / `--force` flags

**Destructive Commands:**
- `app destroy` - Destroys application and all data
- `backup destroy` - Permanently deletes a backup
- `addon destroy` - Destroys service instance and all data

**Confirmation Format:**
```
⚠ WARNING: This will permanently destroy the app 'my-app' and all its data.
This action cannot be undone.

Type the app name to confirm: _
```

**Benefits:**
- Prevents accidental data loss
- Makes consequences clear before execution
- Allows automation with bypass flags
- Follows industry standards (AWS CLI, kubectl, etc.)

**Alternatives Considered:**
- **Soft deletes**: Rejected - adds complexity, doesn't prevent all accidents
- **Undo functionality**: Rejected - not feasible for all operations (e.g., service data)
- **Config file setting**: Rejected - per-command flag is more explicit

### 2. Rich Output Formatting

**Design:**
- Use the [Rich](https://rich.readthedocs.io/) library for enhanced terminal output
- Create new `RichPrinter` class that replaces the basic `Printer`
- Support multiple message types with appropriate styling:
  - **Success**: Green checkmark `✓`
  - **Error**: Red `ERROR:` prefix, sent to stderr
  - **Warning**: Yellow `⚠` prefix
  - **Info**: Blue `ℹ` prefix
  - **Tables**: Colored headers, aligned columns
  - **Panels**: Boxed text for important messages

**Output Message Protocol:**
Messages from server include type field `"t"`:
- `"success"` - Success messages (green)
- `"error"` - Error messages (red, stderr)
- `"warning"` - Warning messages (yellow)
- `"info"` - Info messages (blue)
- `"table"` - Tabular data (Rich Table)
- `"panel"` - Boxed messages (Rich Panel)
- `"progress"` - Progress updates (spinner/bar)

**Benefits:**
- Easier to scan output visually
- Errors immediately visible (red)
- Professional appearance
- Better accessibility (color + icons)

**Alternatives Considered:**
- **Termcolor**: Rejected - less feature-rich than Rich
- **Colorama**: Rejected - only colors, no tables/panels
- **Custom implementation**: Rejected - Rich is battle-tested

### 3. Machine-Readable Output

**Design:**
- Add `--json` flag to output all results as JSON
- JSON output goes to stdout, can be piped to `jq` or parsed by scripts
- All message types preserved in JSON with metadata
- No colors or formatting in JSON mode

**JSON Format:**
```json
[
  {
    "t": "success",
    "text": "App deployed successfully",
    "timestamp": "2025-11-08T14:30:22Z"
  },
  {
    "t": "table",
    "headers": ["Name", "Status", "Port"],
    "rows": [
      ["my-app", "RUNNING", "8000"]
    ]
  }
]
```

**Benefits:**
- Easy integration with scripts
- CI/CD can parse results
- Enables custom tooling
- Preserves all information

**Alternatives Considered:**
- **CSV output**: Rejected - only works for tables
- **XML output**: Rejected - too verbose
- **YAML output**: Rejected - harder to parse than JSON

### 4. Quiet Mode

**Design:**
- Add `--quiet` / `-q` flag to suppress all output except errors
- Only exit code indicates success/failure
- Errors always printed to stderr (even in quiet mode)
- Useful for scripts that only care about success/failure

**Behavior:**
```bash
# Normal mode
$ hop3 deploy my-app
✓ Building application...
✓ Deploying to server...
✓ App deployed successfully

# Quiet mode
$ hop3 deploy my-app --quiet
$ echo $?
0
```

**Benefits:**
- Clean CI/CD logs
- Faster execution (no formatting overhead)
- Standard CLI pattern

**Alternatives Considered:**
- **Verbosity levels (-v, -vv, -vvv)**: Deferred to future enhancement
- **Log file option**: Deferred to future enhancement

### 5. Progress Indicators

**Design:**
- Use Rich Progress API for long-running operations
- Show spinner for operations without known duration
- Show progress bar for operations with stages (build → deploy → start)
- Progress updates sent from server as special message type

**Progress Message Format:**
```json
{
  "t": "progress",
  "text": "Deploying application...",
  "current": 2,
  "total": 3,
  "status": "in_progress"
}
```

**Visual:**
```
Deploying my-app
  ✓ Building application
  ⏳ Deploying to server...  ━━━━━━━━━━━━━━╸━━━━━━  60%
    Starting processes
```

**Benefits:**
- Users know command is working
- Reduces support requests
- Professional appearance
- Matches expectations from modern tools

**Alternatives Considered:**
- **Simple dots (...)**: Rejected - less informative
- **Percentage only**: Rejected - doesn't show what's happening
- **No progress**: Rejected - poor UX

### 6. Client-Side Validation

**Design:**
- Validate inputs before sending to server
- Check for common mistakes with helpful error messages
- Provide suggestions for fixing errors

**Validations:**
- **App names**: Alphanumeric + hyphens only, max 63 chars
- **Deploy command**: Check for `hop3.toml` or `Procfile` existence
- **Backup restore**: Validate backup ID format
- **Service names**: Check format before creating

**Error Message Format:**
```
ERROR: Invalid app name 'my app'

App names must:
  • Contain only lowercase letters, numbers, and hyphens
  • Start with a letter
  • Be between 3 and 63 characters

Did you mean: 'my-app'?
```

**Benefits:**
- Faster feedback (no round-trip to server)
- Better error messages
- Fewer server errors
- Guides users to correct usage

**Alternatives Considered:**
- **Server-side only**: Rejected - slower feedback (round-trip per error)
- **Strict validation**: Rejected - too restrictive
- **No suggestions**: Rejected - less helpful

## Consequences

### Positive

1. **Better User Experience**
   - Professional, modern CLI appearance
   - Clear visual feedback
   - Reduced accidental errors

2. **Automation-Friendly**
   - JSON output enables scripting
   - Quiet mode for CI/CD
   - Programmatic error handling

3. **Reduced Support Load**
   - Better error messages reduce questions
   - Progress indicators reduce "is it stuck?" questions
   - Confirmations prevent accident recovery requests

4. **Industry Standards**
   - Matches expectations from other modern CLIs
   - Familiar patterns for users
   - Professional polish

5. **Extensible Design**
   - Easy to add new message types
   - Framework for future enhancements
   - Clean separation of concerns

### Negative

1. **Increased Complexity**
   - More code to maintain
   - More testing required
   - Additional dependency (Rich)
   - **Mitigation**: Rich is stable, widely-used library

2. **Backward Compatibility**
   - Scripts may break if they parse text output
   - New prompts may block automation
   - **Mitigation**: Provide bypass flags, document migration path

3. **Performance Overhead**
   - Rich formatting has small overhead
   - Validation adds client-side processing
   - **Mitigation**: Minimal (< 100ms), imperceptible to users

4. **Testing Complexity**
   - Interactive prompts harder to test
   - Multiple output modes to test
   - **Mitigation**: Good test fixtures, CI automation

### Trade-offs

1. **Confirmation vs Speed**
   - **Chose**: Confirmation for safety
   - **Trade-off**: Extra step for destructive actions
   - **Benefit**: Prevents costly mistakes

2. **Rich vs Simple**
   - **Chose**: Rich formatting by default
   - **Trade-off**: Slightly larger dependency
   - **Benefit**: Much better UX, industry standard

3. **Client vs Server Validation**
   - **Chose**: Client-side validation for common cases
   - **Trade-off**: Validation logic in two places
   - **Benefit**: Faster feedback, better errors

## Alternatives Considered

### Alternative 1: No Changes

**Keep current simple CLI as-is**

**Rejected because:**
- Users want better UX
- Accidental deletions are real problem
- Automation requires workarounds
- Falls short of modern CLI standards

### Alternative 2: Minimal Changes Only

**Just add confirmation prompts, skip formatting**

**Rejected because:**
- Confirmation alone doesn't address other pain points
- Rich formatting provides significant value
- Partial solution doesn't meet user needs
- Similar effort to implement fully

### Alternative 3: Complete Rewrite

**Rewrite CLI using Click or Typer framework**

**Rejected because:**
- Current architecture works well
- RPC-based design is core advantage
- Migration would break compatibility
- Much larger scope (weeks vs days)

### Alternative 4: Server-Side Prompts

**Have server prompt for confirmation via RPC**

**Rejected because:**
- Breaks client-server separation
- Harder to test
- Requires complex RPC protocol changes
- Client-side is more responsive

## Migration Path

### For Users

**Existing workflows continue to work:**
- Default behavior unchanged for non-destructive commands
- Destructive commands now prompt (add `-y` to scripts)
- Old text output still works (add `--json` for parsing)

**Migration steps:**
1. Update scripts with `-y` flag for destructive commands
2. Update parsing scripts to use `--json` flag
3. Remove custom progress indicators (now built-in)

### For Developers

**New command development:**
1. Use new message types in command responses
2. Mark destructive commands with `destructive = True`
3. Emit progress updates for long operations
4. Include helpful suggestions in error messages

## Future Enhancements

### Verbosity Levels

**Not in initial scope, but planned:**
- `-v` / `--verbose`: Show debug information
- `-vv`: Show even more debug information
- Default: Current level

### Custom Themes

**User-configurable color schemes:**
- Light theme for light terminals
- Dark theme for dark terminals
- Accessibility themes (high contrast)
- Config file: `~/.hop3/theme.toml`

### Command History

**Shell-like command history:**
- Up arrow to recall previous commands
- Searchable history
- Stored in `~/.hop3/history`

### Auto-Completion

**Shell completion for bash/zsh/fish:**
- Complete command names
- Complete app names
- Complete backup IDs
- Installation script

### Progress Persistence

**Resume interrupted operations:**
- Save progress state
- Resume on reconnect
- Useful for long deploys over unstable connections

## References

**Inspiration from:**
- [AWS CLI](https://aws.amazon.com/cli/) - Confirmation prompts, JSON output
- [kubectl](https://kubernetes.io/docs/reference/kubectl/) - Rich output, validation
- [GitHub CLI](https://cli.github.com/) - Modern UX patterns
- [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) - Simplicity focus

**Libraries:**
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [Click](https://click.palletsprojects.com/) - Future consideration
- [Typer](https://typer.tiangolo.com/) - Future consideration
