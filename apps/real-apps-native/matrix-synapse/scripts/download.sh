#!/bin/bash
set -e
echo "Preparing Matrix Synapse..."
mkdir -p data media_store

# requirements.txt is committed, fully pinned (`uv pip compile` from
# `matrix-synapse[postgres]`). Do NOT regenerate it from the bare
# `matrix-synapse[postgres]` here: that resolves to whatever satisfies the
# range today and cannot be reproduced.

echo "Matrix Synapse directories ready (requirements.txt is committed + pinned)"
