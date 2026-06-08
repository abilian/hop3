# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Log compression for per-build log storage (ADR 044 §E).

Full per-phase logs are kept for *every* build, so they're compressed. We use
stdlib ``lzma`` (high ratio, available on every supported Python) and tag each
blob with the algorithm, so a future switch (e.g. to ``zstd`` on 3.14+) can read
old rows without a migration.
"""

from __future__ import annotations

import lzma

ALGO = "lzma"


def compress(text: str) -> tuple[str, bytes, int]:
    """Compress log text. Returns ``(algo, blob, original_size_bytes)``."""
    raw = text.encode("utf-8")
    return ALGO, lzma.compress(raw), len(raw)


def decompress(algo: str, blob: bytes) -> str:
    """Inverse of :func:`compress`."""
    if algo == "lzma":
        return lzma.decompress(blob).decode("utf-8")
    msg = f"Unknown log compression algorithm: {algo!r}"
    raise ValueError(msg)
