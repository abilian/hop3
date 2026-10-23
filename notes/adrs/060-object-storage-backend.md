# ADR 060: Object Storage Backend

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-09-12
- **Related-ADRs**: [021](./021-proxy-plugin-system.md) (plugin protocols), [039](./039-python-deploy-strategies.md) (how a runtime's dependencies are sourced and pinned)

## Context

Hop3's S3 addon gives each application a bucket and credentials scoped to it. The addon was always written against a protocol, `S3Backend`, with the object store behind it treated as replaceable; MinIO was the first implementation and the default.

In 2025 MinIO moved its community edition toward a source-available enterprise tier, and the addon's own package docstring already recorded an intention to replace it on licensing grounds. That intention was never urgent. It became urgent for a different reason.

**MinIO withdrew its public server binaries.** As of September 2026 `dl.min.io` answers **HTTP 410 Gone** for every server path (the pinned release the installer used, and the unversioned `linux-amd64/minio` and `linux-arm64/minio` paths alike), and MinIO's GitHub releases carry no assets at all. There is no Debian or Ubuntu package. Only the `mc` client is still distributed.

The consequence is no service at all: `hop3-install server --with s3` fails during system dependencies, and because a failing `--with` feature aborts the install (correctly; see the fail-loud doctrine), the whole install fails. Every Hop3 server provisioned with S3 was unbuildable, including the Docker target the end-to-end suite provisions.

This is not a version to bump. The distribution channel is gone.

## Decision

**Garage becomes the object store Hop3 installs, and the default `S3Backend`.**

Garage (https://garagehq.deuxfleurs.fr/) is a single static musl binary with no runtime dependencies, S3-compatible, AGPL-3.0, developed by Deuxfleurs for self-hosted and geographically distributed storage. Its releases are published as per-target-triple binaries that can be fetched and pinned.

`MinIOBackend` is kept and remains selectable with `HOP3_S3_BACKEND=minio`, for an operator who runs their own MinIO. The installer no longer provides one, and cannot.

### What the choice rests on

- **It can be installed.** This is the binding constraint. It eliminated MinIO regardless of any other merit.
- **It matches the deployment shape.** One static binary, with no JVM, container or package repository to add. The installer fetches it, writes a config, and runs it under whichever process manager the host has.
- **Its licence is the one MinIO was leaving.** AGPL-3.0 applies to Garage itself, which Hop3 runs as a separate process and talks to over HTTP. It is not linked into Hop3 and does not reach applications, so it does not affect the licence of Hop3 or of anything deployed on it. An operator who objects to running AGPL software can select another backend.
- **Its scope is ours.** Garage targets self-hosting on ordinary hardware, which is the case Hop3 serves.

### Alternatives

**Build MinIO from source at install time.** Keeps the current backend. Costs a Go build on every install, ties the platform to a project that has just demonstrated it will withdraw distribution, and leaves the licensing question that prompted the replacement plan in the first place.

**SeaweedFS.** Apache-2.0, which is more permissive than AGPL and would matter to an operator who redistributes a modified object store. Larger operational surface (master, volume and filer roles) for a single-node deployment, and its S3 gateway is one component among several.

**Drop the bundled object store; require an external S3 endpoint.** Simplest platform, and correct for an operator who already has object storage. It removes a capability from single-server installs, which is the deployment Hop3 exists for. An `s3` addon pointing at a remote endpoint would be a useful addition whichever server is bundled, but it does not answer the replacement question.

## Detailed Design

### Two protocols, not one

Garage exposes two HTTP interfaces. The backend uses both, because neither suffices alone.

The **admin API** (port 3903, bearer token) manages buckets and keys as plain JSON. Bucket creation, key creation, permission grants, listing and per-bucket statistics all go through it.

The **S3 API** (port 3900, SigV4) is the only way to delete objects. This matters because Garage refuses to delete a bucket that still holds any object: 409 from the admin API, `Bucket is not empty` from its CLI, and no force flag. MinIO's `mc rb --force` recursed, so the addon's `delete_bucket` contract ("delete a bucket and all its contents") had a one-line implementation there and needs a real one here.

Three ways to empty a bucket were available: keep `mc`, which is still distributed but is MinIO's own tool, so the replacement would still depend on the thing it replaced; add `boto3`, roughly 15 MB of dependency for two calls; or sign the two required S3 requests directly. The third was taken: about sixty lines covering `ListObjectsV2` and `DeleteObject`, both with empty payloads, using `httpx`, which hop3-server already depends on.

Emptying needs a key with `owner` rights, which the per-application keys do not have. One is minted for the duration of the delete and removed in a `finally`, so a failed delete cannot leave a standing grant on a bucket that still exists.

### Per-application isolation

A Garage key starts with access to nothing; `bucket/allow` grants it read and write on exactly one bucket, and never `owner`, so an application cannot re-grant itself access to a neighbour's data. This is verified against a real node: the integration test writes with a scoped key and confirms a second bucket is refused.

### Installation

Beyond the binary, a single-node Garage needs a config file carrying two secrets and a **cluster layout**. The layout has no MinIO equivalent and is the step most easily missed: until a node is given a role and that role is committed, Garage accepts connections and answers health checks while serving no data. The installer assigns a role sized from the data filesystem's free space, then commits it.

Secrets are read back from an existing `garage.toml`, never regenerated. `rpc_secret` identifies the node to itself across restarts and `admin_token` is what every running hop3-server authenticates with, so a redeploy that rotated them would leave the addon unable to manage the buckets it created. This follows the standing installer rule that a redeploy never rotates secrets or drops operator config.

The admin token is published to the `hop3` user in its own file at `/etc/hop3/garage-admin-token` (0640 root:hop3). `garage.toml` stays 0600 because it also holds the RPC secret; widening it to share the admin token would expose both.

### Ports

Garage listens on 3900 (S3), 3901 (RPC) and 3903 (admin), all bound to loopback. MinIO's 9000 and 9001 are freed. Applications receive an endpoint in their injected credentials, never a hardcoded port, so the change does not reach them.

### Backup and restore

A bucket's backup is a tar of its objects, each with its content type in a PAX header, read with the application's own key. It goes wherever the addon's other dumps go: `hop3 addon s3 dump` and `export`, `clone`, and an app backup. Restore reads the whole archive before touching the bucket, writes every object back, and only then deletes the objects the archive does not hold. A restore that stops part-way leaves the bucket's objects plus part of the archive's, never fewer than it had, and can be run again. A bucket swap would make it atomic; MinIO has no counterpart to Garage's aliases, and a restore that depends on the backend is a cost against it.

The object operations are a small SigV4 client over httpx (`s3api`), shared with the purge that empties a bucket before Garage will drop it. Both run against the server's own store, so no S3 SDK joins the server's dependencies.

## Consequences

An existing server with MinIO-provisioned buckets keeps them: nothing deletes MinIO or its data. `HOP3_S3_BACKEND=minio` continues to address it as long as the operator keeps that MinIO running. No migration path from MinIO data to Garage exists, and none is planned: the two are independent object stores, and copying between them is an `rclone`/`mc mirror` operation an operator can run with credentials from both. A server that wants to move should be treated as a data migration.

Hop3 now ships a pinned download from a project-run URL rather than a distribution package, which is the same reproducibility tier as the other pinned binaries the installer fetches and carries the same risk this ADR exists because of. The pin is bumped by hand.

## Unresolved Questions

- **Should the addon also accept a remote S3 endpoint?** Useful independently of which server is bundled, and a way to make the bundled store optional.
- **Multi-node Garage.** Garage's reason for existing is replication across sites. Hop3 configures one node with `replication_factor = 1`. Nothing here forecloses more, but nothing exercises it either.

## References

- Garage documentation: https://garagehq.deuxfleurs.fr/documentation/
- Garage admin API v1, verified against v1.1.0 while implementing this
- `notes/todo.md`: the MinIO 410 finding, with the probes behind it
