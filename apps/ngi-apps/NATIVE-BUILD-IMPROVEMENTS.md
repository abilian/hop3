# Native Build Improvements Plan

## Current Issues

### 1. Toolchain Detection Required
The `LocalBuilder` requires at least one language toolchain to accept the project:
- Go: needs `go.mod`
- Node: needs `package.json`
- PHP: needs `composer.json`
- Python: needs `requirements.txt` or `pyproject.toml`
- etc.

**Problem**: Apps with vendored dependencies (WordPress, Kanboard, Nextcloud, Matomo) have no marker files.

### 2. No Toolchain Override
There's no way to specify a toolchain in `hop3.toml`. The `builder` field only supports `auto`, `local`, or `docker`.

### 3. PHP Toolchain Too Restrictive
PHP apps without `composer.json` are rejected, even though they're valid PHP applications.

## Proposed Solutions

### Solution A: Enhance PHP Toolchain Detection (Quick Fix)

Modify `PHPToolchain.accept()` to detect PHP projects by:
1. `composer.json` exists, OR
2. `index.php` exists in root, OR
3. Any `.php` file exists in root

```python
def accept(self) -> bool:
    # Current: composer.json only
    if self.check_exists("composer.json"):
        return True
    # New: detect any PHP files
    if self.check_exists("index.php"):
        return True
    php_files = list(self.src_path.glob("*.php"))
    return len(php_files) > 0
```

**Pros**: Simple, backward compatible
**Cons**: Might need to skip `composer install` if no `composer.json`

### Solution B: Add "Generic" Toolchain (Comprehensive Fix)

Create a new `GenericToolchain` that:
1. Accepts when no other toolchain matches AND `hop3.toml` has build commands
2. Just runs the `[build].build` commands without toolchain-specific logic

```python
class GenericToolchain(LanguageToolchain):
    """Fallback toolchain for projects without standard build tools."""

    name = "Generic"

    def accept(self) -> bool:
        # Accept if hop3.toml has build commands and no other toolchain matched
        return self._has_build_commands()

    def build(self) -> BuildArtifact:
        # Just run the build commands from hop3.toml
        # No toolchain-specific logic
        ...
```

**Pros**: Works for any language, flexible
**Cons**: Need to ensure it's checked last (after all other toolchains)

### Solution C: Add `toolchain` Field to hop3.toml (Full Control)

Allow explicit toolchain specification:

```toml
[build]
toolchain = "php"  # Force PHP toolchain
# or
toolchain = "generic"  # Use generic toolchain
```

**Pros**: Full user control
**Cons**: Requires schema update and documentation

## Recommended Implementation Order

1. **Phase 1** (Quick Win): Solution A - Enhance PHP detection
   - Modify `php.py` to accept PHP files without `composer.json`
   - Skip `composer install` if no `composer.json`

2. **Phase 2** (Robustness): Solution B - Add Generic toolchain
   - Create `generic.py` toolchain as fallback
   - Register it to be checked last

3. **Phase 3** (Full Control): Solution C - Add toolchain field
   - Update hop3.toml schema
   - Update config parser
   - Add documentation

## Testing

After implementing, these apps should work:
- **PHP (vendored)**: WordPress, Kanboard, Nextcloud, Matomo, Adminer
- **Go (with go.mod)**: Miniflux ✓, Gitea, Focalboard, Mattermost
- **Node (with package.json)**: Ghost, Etherpad, HedgeDoc, Umami, Wiki.js

## Notes on PHP Apps Without composer.json

These apps ship with all dependencies included:
- **WordPress**: Core + bundled plugins/themes
- **Kanboard**: All PHP files included
- **Nextcloud**: Full distribution with dependencies
- **Matomo**: Pre-built release with all modules
- **Adminer**: Single PHP file, no dependencies

They don't need a "build" step - just:
1. Download/extract the release
2. Configure (create config files)
3. Run with PHP
