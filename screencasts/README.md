# Hop3 screencasts

Terminal recordings of Hop3 demos and tutorials, in [asciicast](https://docs.asciinema.org/manual/asciicast/v3/) format. Each `.cast` file is one run of one demo or one tutorial, recorded by driving the real scripts under [`demos/`](../demos/) and [`docs/tutorials/`](../docs/tutorials/) against a real server — nothing here is typed by hand or re-enacted.

`MANIFEST.md` and `manifest.json` list every recording with its category and source.

## How to view them

**These are asciicast v3.** They were recorded with asciinema 3.x, and tools that only read v2 — including older `asciinema` releases and older builds of the web player — will not open them. Convert first if you hit that (below).

### In a terminal

```bash
# macOS: brew install asciinema — any 3.x release
asciinema play demo-demo34.cast

#   space   pause / resume
#   .       step one event (while paused)
#   ]       skip to the next marker
#   ctrl-c  quit
```

Speed it up, or cap the pauses, if a recording drags:

```bash
asciinema play --speed 2 demo-demo60.cast
asciinema play --idle-time-limit 1 demo-demo60.cast
```

### Without asciinema

Read one as plain text — no player, no timing, useful for grepping or for pasting into an issue:

```bash
asciinema convert -f txt demo-demo34.cast -   # '-' writes to stdout
```

### On the web

The recordings are not yet uploaded anywhere; there are no asciinema.org URLs to link to. To view one in a browser today, either upload it to your own account:

```bash
asciinema auth          # once
asciinema upload demo-demo34.cast
```

…or embed it with [asciinema-player](https://docs.asciinema.org/manual/player/), serving the `.cast` file next to the page. If your player build predates v3 support, convert first:

```bash
asciinema convert -f asciicast-v2 demo-demo34.cast demo-demo34.v2.cast
```

## What is actually watchable right now

**These recordings are a first pass and most of them did not survive it. They are published as-is, unedited, rather than trimmed to the ones that look good — but do not read the file count as a count of finished screencasts.**

`MANIFEST.md` marks all 68 `ok`. That column records only that the recorder started and wrote a file; it does not reflect what is in it. Read from the files themselves, the 68 are:

| State | Count | What is in the file |
|---|---:|---|
| **Clean** | **11** | Ran to completion, exit 0 |
| Ran, ended in failure | 33 | A real session, several minutes, ending on a visible red `FAIL` |
| Nothing recorded | 24 | Interrupted at the prompt (`^C`), some zero bytes — no content at all |

The 33 failures are mostly one cause: 30 tutorials reach their `hop3 deploy` step and hit the recorder's fixed **120-second timeout** (`Expected exit code 0, got -1 / Command timed out after 120s`), with the ~31 steps before it passing. The tutorial itself is not necessarily broken — the recording harness gave the deploy less time than a real deploy takes.

The eleven clean ones:

| Cast | Length | What it shows |
|---|---:|---|
| `demo-demo19.cast` | 2:03 | Docker Go/Gin application |
| `demo-demo28.cast` | 2:31 | MySQL page counter |
| `demo-demo29.cast` | 2:35 | Native Python + MySQL addon |
| `demo-demo32.cast` | 2:22 | Native Python + Redis addon |
| `demo-demo33.cast` | 1:29 | Declarative PostgreSQL provider |
| `demo-demo34.cast` | 1:26 | Declarative MySQL provider |
| `demo-demo35.cast` | 1:41 | Declarative Redis provider |
| `demo-demo59.cast` | 3:19 | Elixir/Plug prerequisites |
| `demo-demo60.cast` | 3:50 | CLI surface tour |
| `tutorial-python-eve.cast` | 0:06 | too short to be a screencast |
| `tutorial-python-litestar.cast` | 0:09 | too short to be a screencast |

So **nine** are worth watching today, all of them demos. Start with `demo-demo60` for the CLI as a whole, or `demo-demo33` for a short one.

## Re-recording

The set is due to be re-recorded. Two things to fix first, both in the harness rather than in what is being demonstrated:

- **Raise the per-step timeout past 120 s** for deploy steps, or make it per-step configurable. This alone accounts for 30 of the 33 failures.
- **Fail the manifest when a recording is empty or ends non-zero**, instead of writing `ok`. A manifest that reports success for a zero-byte file is worse than no manifest: it is what let 57 unusable recordings sit here looking like a finished deliverable.

Recording is unattended and takes roughly an hour and a half of wall clock for the full set against a live server; `^C` at the wrong moment is what produced the 24 empty files.
