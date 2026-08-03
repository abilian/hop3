# hop3-marketplace

Renders the public app catalog site served at **apps.hop3.cloud** from a
`hop3-catalog` checkout.

```bash
uv run hop3-site --catalog ../hop3-catalog/apps --out ../hop3-catalog/public
python3 -m http.server -d ../hop3-catalog/public   # preview
```

The site and the hop3-server dashboard read the same catalog through the same
code: `hop3.server.catalog.loader` and `.taxonomy`. This package adds only the
presentation — Jinja templates, a client-side search index, and static assets.
Anything that changes what an app *is* belongs in `hop3.server.catalog`.

Publication is `make publish` in the catalog repo, which signs the catalog and
deploys `public/` as a Hop3 static app.
