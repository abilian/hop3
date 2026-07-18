#!/bin/bash
# Re-template config.yml on EVERY deploy (ADR 056). Vikunja reads config.yml from
# its working directory; writing it write-once (the old `if [ ! -f config.yml ]`)
# froze security-relevant settings at first-deploy values, so a later change to
# "registration disabled" or the public URL would never take effect on redeploy.
# Regenerating each run keeps those settings authoritative. config.yml holds only
# platform-generated values (DB creds, port, public URL, JWT secret) — no user
# state — so rewriting it is safe. The JWT secret is a STABLE generated env var
# (same value every redeploy), so re-writing it doesn't rotate it. Persistent
# uploads live in ./files, backed by a [[volumes]] persist mount (survives the
# src/ wipe), so config regeneration never touches user data.
set -euo pipefail
cd "$(dirname "$0")/.."

# Fail loud on missing DB credentials injected by the postgres addon: a silent
# empty password would yield a broken deploy that lies about being up.
: "${PGPASSWORD:?Postgres password not injected — attach a [[addons]] type=postgres}"

# Consume the platform-generated, redeploy-stable JWT signing secret (ADR 046).
# Vikunja auto-generates a RANDOM service.JWTSecret at every startup when unset,
# invalidating every issued token on each restart/redeploy. Pin it to ${JWT_SECRET}
# (declared as `[env] JWT_SECRET = { generate = "urlsafe" }`) so sessions survive
# redeploys. Fail loud if absent — a generated [env] var is always injected on a
# real deploy, so a missing value means a broken config, not a valid fallback.
: "${JWT_SECRET:?JWT_SECRET not injected — declare [env] JWT_SECRET = { generate = \"urlsafe\" } in hop3.toml}"

# Consume the platform-injected canonical public URL (https://<host>) so links,
# emails and API/frontend communication point at the real host instead of
# localhost. When no domain is configured (e.g. bare Docker test on a port),
# leave it empty so Vikunja auto-detects it from the request — a valid default,
# and publicurl is not a credential, so a fallback here is legitimate. Vikunja
# expects a trailing slash.
PUBLIC_URL="${HOP3_PUBLIC_URL:-}"
if [ -n "$PUBLIC_URL" ]; then
    case "$PUBLIC_URL" in
        */) ;;
        *) PUBLIC_URL="${PUBLIC_URL}/" ;;
    esac
fi

cat > config.yml << EOF
service:
  interface: ":${PORT:?PORT not injected}"
  # Stable JWT signing secret (ADR 046). Without this, Vikunja generates a random
  # secret at each startup and every issued token is invalidated on restart/
  # redeploy. The value below is generated once and re-injected unchanged, so
  # sessions survive redeploys. (viper reads the key case-insensitively; upstream
  # names it JWTSecret.)
  jwtsecret: "${JWT_SECRET}"
  # Public-facing URL (used in emails and for API/frontend communication).
  # Empty => Vikunja auto-detects it from the incoming request.
  publicurl: "${PUBLIC_URL}"
  # Close open self-registration (ADR 056): a stranger cannot sign themselves up;
  # accounts are created by the provisioned admin. Re-applied every deploy.
  enableregistration: false

database:
  type: postgres
  host: "${PGHOST:?Postgres host not injected}"
  port: ${PGPORT:-5432}
  database: "${PGDATABASE:?Postgres database not injected}"
  user: "${PGUSER:?Postgres user not injected}"
  password: "${PGPASSWORD}"

files:
  basepath: ./files
EOF

echo "Vikunja config.yml written (registration disabled, publicurl='${PUBLIC_URL:-<auto>}')"
