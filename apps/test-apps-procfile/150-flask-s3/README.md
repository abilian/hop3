# Flask S3 Smoke Test App

A minimal Flask application that exercises the Hop3 S3 addon by doing
an object round-trip: PUT a small payload, GET it back, compare.

## What it validates

- `addons:create s3 <name>` provisioned a bucket on the server's S3
  backend (MinIO by default)
- `addons:attach <addon> <app>` injected the `S3_*` env vars into
  this app's runtime environment
- The app can actually reach the S3 endpoint using the injected
  credentials and read/write objects

## Endpoints

| Path      | Behavior                                                     |
|-----------|--------------------------------------------------------------|
| `/`       | Puts a test object, gets it back, returns "S3 addon OK".     |
| `/config` | Returns the S3 endpoint/bucket/region and whether credentials are present. |

## Prerequisites

- Hop3 server installed with `--with s3`
- An S3 addon created: `hop3 addons:create s3 myapp-storage`
- This app deployed and the addon attached: `hop3 addons:attach myapp-storage <app>`

## Running locally (without Hop3)

Set the env vars manually:

```bash
export S3_ENDPOINT=http://127.0.0.1:9000
export S3_ACCESS_KEY=your-key
export S3_SECRET_KEY=your-secret
export S3_BUCKET=your-bucket
export S3_REGION=us-east-1

pip install -r requirements.txt
python -m flask --app app run
curl http://127.0.0.1:5000/
```
