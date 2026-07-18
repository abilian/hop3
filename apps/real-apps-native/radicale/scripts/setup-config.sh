#!/bin/bash
# Radicale setup (ADR 056): re-template the config on every deploy so config
# changes always apply, and bootstrap the admin htpasswd entry from the
# credential Hop3 generated.
set -e
cd "$(dirname "$0")/.."

# The generated admin credential is required. A missing credential must abort
# the deploy loudly rather than silently produce a server nobody can log into
# (or, worse, fall back to anonymous access).
: "${HOP3_ADMIN_USER:?ERROR: HOP3_ADMIN_USER is required (see [admin] section, ADR 056)}"
: "${HOP3_ADMIN_PASSWORD:?ERROR: HOP3_ADMIN_PASSWORD is required (see [admin] section, ADR 056)}"

# Always (re)write the config so switching auth on redeploy takes effect. Auth
# is htpasswd/bcrypt: this closes the previous anonymous read/write to all data.
cat > config << EOF
[server]
hosts = 0.0.0.0:${PORT:-8080}

[auth]
type = htpasswd
htpasswd_filename = users
htpasswd_encryption = bcrypt

[storage]
filesystem_folder = collections
EOF

# Create the admin htpasswd entry from the injected credential, create-if-absent
# so redeploys keep the same (already-surfaced) password rather than rotating it.
# bcrypt (from radicale[bcrypt]) hashes the generated password.
if [ ! -f users ]; then
    hash=$(python -c "import bcrypt, os; print(bcrypt.hashpw(os.environ['HOP3_ADMIN_PASSWORD'].encode(), bcrypt.gensalt()).decode())")
    printf '%s:%s\n' "${HOP3_ADMIN_USER}" "${hash}" > users
fi

echo "Radicale configuration ready"
