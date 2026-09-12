# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
S3-compatible object storage addon for Hop3.

Provides per-app S3 buckets with scoped credentials. The plugin is
backend-agnostic: see ``backend.py`` for the ``S3Backend`` protocol, and
``HOP3_S3_BACKEND`` to choose one.

**The default backend is Garage** (https://garagehq.deuxfleurs.fr/) — a
single static Rust binary, AGPL, built for self-hosting. It replaced MinIO
in September 2026, and not only on licensing grounds: MinIO withdrew its
public server binaries, so `--with s3` could no longer be installed at all.
`dl.min.io` answers 410 for every path and MinIO's GitHub releases publish
no assets; only its `mc` client is still distributed.

``MinIOBackend`` is kept for an operator running their own MinIO, selected
with ``HOP3_S3_BACKEND=minio``. The installer does not provide one. See
ADR 060 for the decision and the AGPL implication.
"""
