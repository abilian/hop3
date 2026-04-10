# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""S3-compatible object storage addon for Hop3.

Provides per-app S3 buckets with scoped credentials. The default
backend is MinIO (chosen for maturity and wide compatibility), but the
plugin is designed to be backend-agnostic: see ``backend.py`` for the
``S3Backend`` protocol.

**Licensing note:** MinIO's licensing moved toward a source-available
enterprise tier in 2025. For sovereignty-focused deployments we plan
to replace the default backend with `Garage <https://garagehq.deuxfleurs.fr/>`_
(genuinely AGPL, single Rust binary) or SeaweedFS (Apache 2). The
``S3Backend`` protocol makes that swap a plugin registration change,
not a rewrite.
"""
