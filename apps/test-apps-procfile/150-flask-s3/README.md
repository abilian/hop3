# Flask S3 Smoke Test App

A Flask application that exercises the Hop3 S3 addon through the
operations a real application performs: write, read back, list,
overwrite, delete.

## What it validates

- `hop3 addon create s3 <name>` provisioned a bucket on the server's S3
  backend (Garage by default — see ADR 060)
- `hop3 addon attach <addon> --app <app>` injected the `S3_*` env vars
  into this app's runtime environment
- The app can reach the S3 endpoint with the injected credentials and
  write, read, list, overwrite and delete objects
- **Keys that break naive URL encoding and signing** — spaces, `+`,
  `%`, quotes, `~`, non-ASCII. This is the point of the app, not
  decoration: a round-trip on `hello.txt` passes against almost any
  implementation. The Garage backend double-encoded the key on delete,
  so the signature covered `a%252Bb.txt` while the request said
  `a%2Bb.txt`; every test in the suite used a safe key, so nothing
  caught it until a bucket could not be emptied and destroying an app
  left its data behind.

## Endpoints

| Path      | Behavior                                                     |
|-----------|--------------------------------------------------------------|
| `/`       | Writes, reads, lists, overwrites and deletes; "S3 addon OK". |
| `/config` | Returns the S3 endpoint/bucket/region and a credentials token. |

## Prerequisites

- Hop3 server installed with `--with s3`
- An S3 addon created: `hop3 addon create s3 myapp-storage`
- This app deployed and the addon attached: `hop3 addon attach myapp-storage --app <app>`

## Running locally (without Hop3)

Set the env vars manually:

```bash
export S3_ENDPOINT=http://127.0.0.1:3900
export S3_ACCESS_KEY=your-key
export S3_SECRET_KEY=your-secret
export S3_BUCKET=your-bucket
export S3_REGION=garage

pip install -r requirements.txt
python -m flask --app app run
curl http://127.0.0.1:5000/
```
