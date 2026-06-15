# flask-volume — persistent `[[volumes]]` smoke test

Proves Hop3's declarative persistent volumes (ADR 046 §2) through a real deploy.

`hop3.toml` declares a volume backing `data/store`:

```toml
[[volumes]]
name = "store"
target = "data/store"
```

Hop3 links `data/store` to `<app>/volumes/store/` (outside `src/`, so it
survives the redeploy that wipes `src/`). The app serves **`VOLUME OK`** only
when `data/store` resolves under `.../volumes/store` *and* is writable — which
`[[test.validations]]` asserts. Survival across redeploys is covered by the
server unit tests.

Endpoints:

- `GET /` — `VOLUME OK` (200) when the volume is mounted and writable.
- `GET /config` — echoes where `data/store` resolves to.
