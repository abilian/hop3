#!/bin/bash
set -e
echo "Preparing Radicale..."
mkdir -p collections

# requirements.txt is committed, fully pinned (`uv pip compile` from
# `radicale[bcrypt]` — the [bcrypt] extra is needed for htpasswd bcrypt
# verification and for hashing the admin password in setup). Do NOT
# regenerate it from the bare `radicale[bcrypt]` here: that resolves to
# whatever satisfies the range today and cannot be reproduced.

echo "Radicale directories ready (requirements.txt is committed + pinned)"
