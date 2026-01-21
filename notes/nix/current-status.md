# NixOS Support - Current Status

## Overview

Hop3 currently supports NixOS for both development and CI testing, but requires special handling because `uv` downloads dynamically linked binaries that don't work on NixOS without `nix-ld`.

## Build Backend Strategy

The project uses `uv_build` as the build backend in all `pyproject.toml` files to stay consistent with uv as the project management tool. However, NixOS builds patch these files at build time to use `hatchling` instead.

### Why This Approach?

1. **uv_build binaries are dynamically linked** - When pip or uv installs `uv-build`, it downloads pre-built binaries that expect a standard FHS filesystem layout. NixOS doesn't have `/lib64/ld-linux-x86-64.so.2`.

2. **hatchling is pure Python** - It works everywhere without dynamic linking issues.

3. **Project consistency** - Keeping `uv_build` in the source files means developers using uv on standard Linux/macOS have the best experience.

## Files Involved

### `.builds/nixos.yml` (SourceHut CI)

The test task patches all `pyproject.toml` files before running pip install:

```bash
patch_pyproject() {
  # Replace uv-build with hatchling
  sed -i "s|requires = \[\"uv-build>=.*\"\]|requires = [\"hatchling\"]|g" "$pyproject"
  sed -i "s|build-backend = \"uv_build\"|build-backend = \"hatchling.build\"|g" "$pyproject"

  # Remove [tool.uv.build-backend] section
  sed -i "/\[tool\.uv\.build-backend\]/,/^$/d" "$pyproject"

  # Add hatchling wheel config
  echo "[tool.hatch.build.targets.wheel]" >> "$pyproject"
  echo "packages = [\"src/$pkg_name\"]" >> "$pyproject"
}
```

The CI also uses `nixpkgs.ruff` instead of pip-installed ruff (same dynamic linking issue).

### `flake.nix` (Nix Package Definitions)

The `postPatch` sections in `hop3-cli` and `hop3-server` package definitions do the same patching:

- Replace `uv-build` with `hatchling`
- Replace `uv_build` backend with `hatchling.build`
- Remove `[tool.uv.build-backend]` section
- Add `[tool.hatch.build.targets.wheel]` config
- Additional nixpkgs-specific patches (e.g., `granian` → `uvicorn`, remove unavailable deps)

## Development on NixOS

For local development on NixOS, two options exist:

1. **Enable nix-ld** (recommended):
   ```nix
   programs.nix-ld.enable = true;
   ```
   Then use the default dev shell: `nix develop`

2. **Use FHS shell** (if nix-ld unavailable):
   ```bash
   nix develop .#fhs
   ```

## CI Test Coverage

The NixOS CI runs:
- `nix build .#hop3-cli` - Verifies Nix package builds
- `nix build .#hop3-server` - Verifies Nix package builds
- `pytest packages/hop3-cli/tests` - Unit tests
- `pytest packages/hop3-server/tests/a_unit` - Unit tests
- `ruff check` - Linting

## Known Limitations

1. **No E2E tests on NixOS CI** - Docker-based tests aren't run on SourceHut NixOS builders.

2. **Patching adds complexity** - The build-time patching is (currently?) necessary but makes the CI config more complex.

3. **Dependency gaps** - Some dependencies aren't in nixpkgs (`cyclonedx-bom`, `mysql-connector-python`, `uwsgi`) and are removed during Nix builds.

## Alternative Considered

We considered switching all `pyproject.toml` files to use `hatchling` permanently. This would:
- Simplify NixOS CI (no patching needed)
- Work with uv (which supports any PEP 517 backend)

However, we chose to keep `uv_build` for consistency with uv as the primary project management tool.
