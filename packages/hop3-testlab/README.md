# hop3-testlab

The Hop3 **Test Lab** — a web dashboard + scheduler that runs the nightly test suite against cloud targets and makes every failure actionable by morning.

Implements [ADR 044](../../notes/adrs/044-nightly-test-lab.md); technical spec in [`local-notes/specs/testlab-specs.md`](../../local-notes/specs/testlab-specs.md). It is a thin web + scheduler + worker shell over the `hop3-testing` functional core (one engine, one store), built with the same stack as `hop3-server` (Litestar + Dishka + Advanced-Alchemy).

## Run

```bash
hop3-testlab serve            # dev server on 127.0.0.1:8001
hop3-testlab serve --reload
```
