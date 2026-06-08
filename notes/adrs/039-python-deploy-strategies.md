# ADR 039: Python Deploy Strategies — Clarify and Make Explicit

**Status**: Active — Phase 1 landed (2026-04-15); Phases 2–3 deferred to 0.6
**Type**: Feature
**Created**: 2026-04-15
**Updated**: 2026-04-22
**Related-ADRs**: 001 (config files), 002 (`hop3.toml` format), 004 (development tooling), 030 (two-level build architecture), 035 (build artifacts as runtime contract), 036 (CLI ergonomics)

## Revisions

- v1.2: Proposed-CLI examples migrated to ADR 036 space form (2026-04-22).
- v1.1: Phase 1 implemented (2026-04-15).
- v1.0: Original design (2026-04-15)

## Context

Hop3's Python language toolchain (`packages/hop3-server/src/hop3/toolchains/python.py`) decides how to install an application's dependencies by inspecting the source tree at build time. The current decision tree is:

1. If `uv.lock` exists and `uv` is installable → `uv sync --frozen --reinstall`
2. Else if `requirements.txt` exists → `pip install --upgrade -r requirements.txt`
3. Else if `pyproject.toml` exists → `pip install --upgrade .`
4. Else → `FileNotFoundError`

This works for a narrow slice of Python apps. It breaks down — sometimes loudly, often silently — in several real cases encountered during the 0.5 application-packaging effort:

### Case 1: Poetry-managed projects

A `pyproject.toml` that declares dependencies under `[tool.poetry.dependencies]` (Poetry-native, no PEP-621 `[project]` table) reaches path 3 of the decision tree. `pip install .` resolves no runtime dependencies because pip reads PEP-621 `[project]`, not `[tool.poetry]`. The install "succeeds" with an empty venv, then crashes at runtime with `ModuleNotFoundError: Django` or similar. **GlitchTip** hit this in W16. Poetry is still a meaningful share of the Python ecosystem (approximately a third of package-manager usage per the 2025 Python Developer Survey); Sentry, GlitchTip, many mid-sized Django shops use it.

### Case 2: `requirements.txt` is three different contracts

A `requirements.txt` in the wild may be:

- **Abstract**: `Django>=4.0` — pip resolves the latest compatible version on every deploy; deploys are non-reproducible.
- **Fully frozen**: `Django==4.2.7` — intent is to pin, but `pip install --upgrade -r requirements.txt` ignores the pin and upgrades anyway.
- **`pip-compile` output with hashes**: integrity-checked; `--upgrade` silently strips the integrity guarantee.

The toolchain treats all three identically. The abstract case gives moving targets across deploys; the frozen case loses pins; the hashed case loses integrity. Silent behavioural divergence.

### Case 3: `requirements.txt` vs `pyproject.toml` precedence

When both files exist, `requirements.txt` wins silently. The comment in the code (L217-219) explains this was added to defend against "stray pyproject.toml" files. This is the same category of mistake as the bundler name-collision of W16: silent override rather than explicit error. An operator who added a pyproject.toml *expecting* it to drive the build gets a different build and no signal.

### Case 4: `uv sync` without `--no-dev`

`uv sync --frozen --reinstall` installs dev dependencies alongside runtime ones. Deployed venvs carry pytest, ruff, type-checkers, etc. This wastes disk and inflates the closure for the Nix variants; it also broadens the attack surface.

### Documentation gap

All 13 Python tutorials under `docs/src/tutorials/python/` teach the same pattern: create a venv, `pip install X`, then `pip freeze > requirements.txt`. This is a 2014 workflow. The tutorials do not cover Poetry, uv, lockfiles, or reproducibility. Users coming from modern Python tooling have no tutorial path; users following the tutorials produce abstract `requirements.txt` files that suffer from Case 2 above.

### What's been tried so far

Individual apps (Bugsink, GlitchTip) have worked around these cases in app-level scripts (e.g. emitting `requirements.txt` from Poetry's lockfile). These workarounds are repeatable but uncoordinated — each packager solves the problem in their own way, and the toolchain is none the wiser.

## Decision

We clarify the Python deployment surface along four axes:

1. **Freeze at packaging time, not at build time.** The packager's intent — which versions to deploy — is captured in the app's source tree in a form that the deployer can read without further resolution. The deployer installs what's declared; it does not compute what should be installed.
2. **Make the install strategy explicit when ambiguous.** Ambiguity (both `requirements.txt` and `pyproject.toml`, or a pyproject with both `[project]` and `[tool.poetry]` sections) surfaces as a `Diagnosis`, not a silent choice.
3. **uv first, Poetry supported-but-deprecated, pip-freeze workflow documented but discouraged.** The default new-app recipe is uv. Poetry is a recognised inbound format with a first-class conversion path. Abstract `requirements.txt` is accepted but warned on.
4. **Users can override detection.** `[build.python].strategy` in `hop3.toml` lets packagers state the intended install path when the auto-detection would be ambiguous or wrong.

### Config surface

New optional field in `hop3.toml`:

```toml
[build.python]
strategy = "uv-sync"          # one of: uv-sync | requirements | pyproject | poetry-export
```

Semantics:

| Value | What the toolchain does |
|-------|------------------------|
| `uv-sync` | `uv sync --frozen --no-dev`. Requires `uv.lock`. |
| `requirements` | `pip install --no-deps -r requirements.txt` when the file has pins; `pip install -r requirements.txt` otherwise (and emit a warning — see lint rules below). |
| `pyproject` | `pip install --no-deps .`. Requires PEP-621 `[project]` with a populated `dependencies` list. |
| `poetry-export` | Look for a pre-generated `requirements.txt` produced by the packager via `poetry export`; if absent, emit a `Diagnosis` telling the operator to run `poetry export --only=main --without-hashes -f requirements.txt -o requirements.txt` at packaging time and commit the result. |

Omitting `[build.python].strategy` invokes auto-detection. Auto-detection rules:

1. `uv.lock` present → `uv-sync`.
2. `requirements.txt` present AND `pyproject.toml` absent → `requirements`.
3. `pyproject.toml` present AND `requirements.txt` absent AND `[project].dependencies` populated → `pyproject`.
4. `pyproject.toml` present with `[tool.poetry]` AND no `[project]` → **error** with a `Diagnosis` pointing at `strategy = "poetry-export"` and the conversion command.
5. Both `requirements.txt` and `pyproject.toml` present → **error** with a `Diagnosis` asking the operator to pick a strategy explicitly.
6. Neither → **error** (unchanged).

### Install changes

- `uv sync` gains `--no-dev` (or `--no-group dev` on uv 0.5+).
- `pip install ... -r requirements.txt` drops `--upgrade`. If the packager wants un-pinned behaviour, they get it; if they want pinned behaviour, we honour it. No silent override.
- `pip install ... .` drops `--upgrade` for the same reason.
- `--no-deps` is used when a lockfile or fully-pinned requirements file is in play (the lockfile is authoritative; pip's resolver should not second-guess).

### Lint rules

Added to `hop3 app check` (and reported as warnings, not build-time errors):

- **Abstract requirements**: `requirements.txt` contains at least one line without `==` or `===` pin. Warning: *"deploys will produce different closures across time. Consider freezing with `pip-compile` or `uv pip compile`."*
- **Ambiguous metadata**: both `requirements.txt` and `pyproject.toml` present with no `[build.python].strategy`. Warning: *"set `[build.python].strategy` to disambiguate; auto-detect will error in build."*
- **Poetry without lockfile in-tree**: pyproject has `[tool.poetry]` but no companion exported `requirements.txt`. Warning: *"export the Poetry lockfile once with `poetry export --only=main`, commit, redeploy."*

### Tutorials

Three deliverables:

- Default Python tutorial becomes **uv-based**: `uv init`, `uv add <deps>`, `uv lock`, deploy. One tutorial per framework (Flask, Django, FastAPI) using this path.
- One **Poetry → Hop3** migration tutorial: `poetry export --only=main --without-hashes -f requirements.txt -o requirements.txt`, commit, add `[build.python].strategy = "requirements"`, deploy.
- One **legacy requirements.txt** tutorial for existing projects: explicit freezing step (`uv pip compile` or `pip-compile`), then deploy.

Tutorials that currently teach `pip freeze > requirements.txt` as the production workflow are rewritten.

## Deferred

**`hop3 app freeze` client-side helper.** Worth doing — it would turn "run `poetry export`, commit the file, redeploy" into `hop3 app freeze` — but it requires the relevant toolchain (`uv`, `poetry`, `pip-compile`) on the packager's client machine and would have to be replicated for the other languages Hop3 supports (Node via `npm shrinkwrap` / `pnpm lock`, Ruby via `bundle lock`, etc.). The abstract mechanism is "a per-language freeze step"; designing it coherently belongs in a separate ADR rather than riding along with Python-specific changes.

## Non-goals

- **Replacing the Python toolchain runtime.** uWSGI-vs-Granian lives in ADR 023; this ADR is only about how dependencies get into the venv.
- **Hermetic Python builds via Nix.** The `python-venv` template remains Tier-2 (uses `__noChroot` for pip). Migrating to `buildPythonApplication` with vendored deps is future work outside this ADR.
- **Per-app Python version selection beyond `_find_best_python()`.** An app that needs Python 3.11 specifically (not "whatever's newest on the host") needs a different mechanism; out of scope.

## Consequences

### Benefits

- **Reproducible deploys** for any app that commits a lockfile or frozen `requirements.txt`. The same source tree produces the same venv across machines and time.
- **No silent behavioural divergence** between abstract and frozen `requirements.txt`. The packager's intent is honoured.
- **Clear path for Poetry users** — explicit conversion step, one-time, idempotent on re-deploy.
- **Doc path that matches 2026 Python practice** — uv first, lockfiles central, tutorials teach what newcomers should actually do.

### Drawbacks

- **Breaking change for existing deployed apps with abstract `requirements.txt` and `--upgrade` behaviour.** A Phase-1 change that drops `--upgrade` changes semantics: apps that were quietly getting newer library versions on each deploy will stop doing so. Operators will see a change the first time they deploy after the upgrade. Mitigation: call this out in the 0.5.x changelog; document the workaround (delete `requirements.txt`, re-freeze).
- **Both-files-present now errors.** Apps in the real-world catalogue may today have both files. Mitigation: Phase-1 patch release comes with a migration note + a one-line addition (`[build.python].strategy = "requirements"` or `"pyproject"`) for affected apps. Grep the in-tree test corpus before the change; the fleet is small enough to do this by hand.

### Risks

- **Poetry path complexity.** `poetry export` has subtle flags (`--only`, `--without`, `--with`, `--without-hashes`) and has broken behaviour historically. We standardise on one invocation; we do *not* run poetry inside Hop3 itself.
- **uv stability.** uv is young (< 2 years at time of writing); its CLI has changed between minor versions (the `--no-dev` vs `--no-group dev` transition is an example). We pin to a compatible-range in the Hop3 installer rather than tracking head.
- **Tutorial rewrite scope.** 13 tutorials × 2-3 passes for consistency is a real chunk of doc work, not a code task. Schedule it separately from Phase 1/2.

## References

- Python toolchain source: `packages/hop3-server/src/hop3/toolchains/python.py`.
- Current Python tutorials: `docs/src/tutorials/python/`.
- Companion ADRs: 001 (config files), 002 (`hop3.toml` format), 030 (two-level build architecture), 035 (runtime contract).
