# Hop3 — Slide Decks

Presentations about Hop3, written in Markdown and rendered with [Prezo](https://github.com/abilian/prezo) or [Marp](https://marp.app/). Each deck declares its own renderer in its front matter (`marp: true` → Marp, otherwise Prezo), and the Makefile routes the build automatically.

## Decks

| File | Title | Venue | Renderer |
|------|-------|-------|----------|
| `2026-ow2con-ngi-zapp.md` | Sovereign, Reproducible Application Deployment | NGI Zero peer talk / OW2con 2026 | Prezo (nord) |
| `2025-ow2con-hop3.md` | Empowering Digital Sovereignty | OW2con 2025 | Marp (gaia) |
| `2025-osxp-hop3.md` | From Self-Hosting Complexity to Production-Ready Sovereignty | Open Source Experience 2025 | Marp (gaia) |

## Layout

```
slides/
├── Makefile                  # build & present the decks
├── README.md                 # this file
├── 2026-ow2con-ngi-zapp.md   # deck — Prezo
├── 2025-ow2con-hop3.md       # deck — Marp
├── 2025-osxp-hop3.md         # deck — Marp
├── images/                   # figures referenced by the decks
└── sandbox/                  # scratch space, not part of any deck
```

## Prerequisites

- **Prezo** — for the Prezo decks: `uv tool install prezo` (or `pipx install prezo`).
- **Marp CLI** — for the Marp decks: `npm install -g @marp-team/marp-cli`.

A recent Chrome/Chromium is used as the PDF backend by both tools.

## Usage

Run `make` (or `make help`) to list every target; it also prints which decks use which renderer:

```bash
make            # show help
make pdf        # export every deck to PDF (auto-routes Prezo/Marp)
make html       # export every deck to HTML
make present    # open a Prezo deck in the live TUI presenter
make clean      # remove generated PDF/HTML exports
```

### Presenting live

`make present` opens a deck in Prezo's terminal presenter with a 10-minute pacing budget. It defaults to a Prezo deck (only Prezo has the live presenter):

```bash
make present                       # first Prezo deck
make present DECK=2026-ow2con-ngi-zapp.md
```

Marp decks are best previewed with `marp --preview <deck>.md` or the Marp VS Code extension.

### Building a single deck

The deck filename maps directly to its output, so you can build just one — the renderer is auto-detected:

```bash
make 2025-ow2con-hop3.pdf                 # built with Marp
make 2026-ow2con-ngi-zapp.pdf             # built with Prezo
make open DECK=2026-ow2con-ngi-zapp.md    # build + open the PDF (macOS)
```

## Configuration

Override any of these on the command line, e.g. `make pdf SIZE=120x40`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SIZE` | `100x30` | Prezo export geometry (terminal cells, `WxH`) |
| `PREZO_FLAGS` | `--size $(SIZE)` | Flags passed to every Prezo export |
| `MARP_FLAGS` | `--allow-local-files` | Flags passed to every Marp export |
| `TIME_BUDGET` | `10` | Minutes shown by the live pacing indicator |
| `DECK` | first Prezo deck | Deck targeted by `present` / `open` |
| `PREZO` / `MARP` | `prezo` / `marp` | Renderer binaries |

> **Note on `--no-emoji`:** earlier build notes used `prezo --export pdf --no-emoji ...`,
> but the installed Prezo (2026.4.2) does not accept that flag, so it is omitted.
> If your Prezo build supports it, re-enable it with
> `make pdf PREZO_FLAGS="--no-emoji --size 100x30"`.

## Notes

- All figures referenced by the decks live in `images/`; the Marp decks read them at build time via `--allow-local-files`.
- Exported PDFs/HTML are build artifacts — regenerate them with `make pdf`; no need to commit them.
- For Prezo decks, speaker notes live after `???` in each slide and are picked up by the presenter view.
