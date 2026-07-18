#!/bin/bash
set -e
cat > .env << EOF
APP_KEY=$(php artisan key:generate --show 2>/dev/null || echo "base64:$(head -c 32 /dev/urandom | base64)")
APP_URL=${APP_URL:-http://localhost:${PORT:-8080}}
APP_ENV=production
APP_DEBUG=false
DB_CONNECTION=mysql
DB_HOST=${MYSQL_HOST:-localhost}
DB_PORT=${MYSQL_PORT:-3306}
DB_DATABASE=${MYSQL_DATABASE:-bookstack}
DB_USERNAME=${MYSQL_USER:-bookstack}
DB_PASSWORD=${MYSQL_PASSWORD:-}
EOF
php artisan migrate --force

# ADR-056 admin bootstrap.
# BookStack's create_users_table migration seeds a well-known default admin
# (admin@admin.com / password). Reset that row in place to the Hop3-generated
# credentials so no default admin ever survives. `bookstack:create-admin` can't
# be used here because it rejects an existing email; updating the row is the
# idempotent path. Fail loud if the injected credentials are missing.
: "${HOP3_ADMIN_USER:?ADR-056 admin bootstrap requires HOP3_ADMIN_USER}"
: "${HOP3_ADMIN_EMAIL:?ADR-056 admin bootstrap requires HOP3_ADMIN_EMAIL}"
: "${HOP3_ADMIN_PASSWORD:?ADR-056 admin bootstrap requires HOP3_ADMIN_PASSWORD}"

# Credentials are read from the environment (getenv) inside tinker so the
# password never appears in the process argv. On a fresh deploy the default
# admin@admin.com row is reset; on redeploy it is already gone, so the real
# admin (matched by the injected email) is reset in place -> idempotent.
php artisan tinker --execute '
$email = getenv("HOP3_ADMIN_EMAIL");
$name  = getenv("HOP3_ADMIN_USER");
$pass  = getenv("HOP3_ADMIN_PASSWORD");
$u = \BookStack\Users\Models\User::where("email", "admin@admin.com")->first()
   ?? \BookStack\Users\Models\User::where("email", $email)->first();
if ($u === null) { throw new \RuntimeException("BookStack admin bootstrap: no admin user to reset"); }
$u->email = $email;
$u->name = $name;
$u->password = \Illuminate\Support\Facades\Hash::make($pass);
$u->save();
'

# Verify the default admin is gone and the generated credentials authenticate.
# This is the fail-loud gate: it does not rely on tinker propagating an exit code.
admin_check=$(php artisan tinker --execute '
$email = getenv("HOP3_ADMIN_EMAIL");
$pass  = getenv("HOP3_ADMIN_PASSWORD");
$leftover = \BookStack\Users\Models\User::where("email", "admin@admin.com")->exists();
$admin = \BookStack\Users\Models\User::where("email", $email)->first();
echo (!$leftover && $admin !== null && \Illuminate\Support\Facades\Hash::check($pass, $admin->password)) ? "ADMIN_OK" : "ADMIN_FAIL";
')
case "$admin_check" in
  *ADMIN_OK*) : ;;
  *) echo "BookStack admin bootstrap failed: default admin not neutralized or generated credentials not applied" >&2; exit 1 ;;
esac

echo "BookStack configuration created"
