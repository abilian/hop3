# Writing CHANGES.md

The file is read by someone deciding whether to upgrade, and by someone who just did and is wondering what moved. Our own record of the work is git. Everything below follows from that.

## What an entry is

**One entry per user-visible change.** Five fixes that together made one capability work are one entry.

**Lead with what the reader does.** "Delete `[run].start` from a PHP recipe" is the sentence they act on. How the old code failed is archaeology: it belongs in the commit message and the code comment, both of which are one `git log -S` away when someone needs it.

**Name the thing in their file.** `[build].document-root`, `hop3 login`, `DATABASE_URL`. A reader greps the changelog for the key they wrote.

**Say what breaks and how to migrate**, in the entry itself. A breaking change buried in prose is a support ticket.

## The category is a claim about the reader

Keep a Changelog's headings (Added, Changed, Deprecated, Removed, Fixed, Security) each make a claim. **Fixed** tells a reader their installation was broken. Only put something there if it was, on a version they could have been running.

A defect in a feature nobody could reach yet belongs to that feature. Five entries of ours described bugs in a php-fpm runtime that no deployed app had ever been served by, because every recipe still declared its own start command. Listed under Fixed they would have told every operator their PHP apps had been broken, which was false. They became one Added entry.

**Claim only what shipped.** An entry written while the work is in flight is a promise the file cannot keep.

## Housekeeping

- `## [Unreleased]` at the top; rename it to the version with an ISO date at release.
- Newest release first.
- Write the entry in the same change that ships the code. A changelog updated later is a changelog written from a diff, which is how it turns back into a log of our work.
- One `CHANGES.md`. A second copy under `docs/` drifts; symlink it.

## Prose

The published changelog is prose, so it goes through the prose gate the same way code goes through `make lint`:

```sh
proselinter CHANGES.md
```

The tics it catches here are the ones that creep in when an entry is written from a debugging session: em-dash incises, `X instead of Y` antithesis, comma splices bolted onto a sentence that had already finished. Run it before the commit.
