#!/bin/bash
# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
#
# Snapshot everything a Hop3 server needs to be put back the way it was:
# the control-plane database, every config and secret file, the service
# units, the proxy and uWSGI trees, the apps tree, and a dump of each backing
# service that is installed. Meant to run as root on the server right before
# a platform upgrade, and safe to run at any other time: it reads, it never
# stops or restarts anything.
#
# Usage (on the server, as root):
#   hop3-server-backup.sh [--label NAME] [--dest DIR] [--skip-apps] [--docker-volumes]
#
#   --label NAME       Folder name suffix, e.g. pre-0.7.3 (default: the date).
#   --dest DIR         Where to write (default: /var/backups/hop3/<host>-<label>).
#   --skip-apps        Do not archive the apps tree (a platform upgrade never
#                      touches it; a disaster-recovery snapshot wants it).
#   --docker-volumes   Also archive every Docker volume (opt-in: can be large,
#                      and needs the busybox image, pulled if absent).
#
# Every step prints ok / skip / FAIL. A skip names what was not there (no
# MySQL installed, no Docker). A FAIL stops the script with a non-zero exit,
# so a backup that says it finished is complete. The result directory is
# mode 0700: it holds every secret the server has.
#
# Restore notes are written to RESTORE.md inside the snapshot.

set -euo pipefail

LABEL=""
DEST=""
SKIP_APPS=0
DOCKER_VOLUMES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --label) LABEL="$2"; shift 2 ;;
        --dest) DEST="$2"; shift 2 ;;
        --skip-apps) SKIP_APPS=1; shift ;;
        --docker-volumes) DOCKER_VOLUMES=1; shift ;;
        -h|--help) sed -n '5,27p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

ok()   { printf '  ok    %s\n' "$*"; }
skip() { printf '  skip  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; exit 1; }
# The file Redis saves to, from its config (Debian /etc/redis/redis.conf,
# Fedora /etc/redis.conf); read there because a stopped Redis cannot say.
redis_dump_path() {
    local conf dir file
    for conf in /etc/redis/redis.conf /etc/redis.conf; do [ -f "$conf" ] && break; done
    [ -f "$conf" ] || fail "Redis has no config at /etc/redis/redis.conf or /etc/redis.conf"
    dir="$(awk '$1 == "dir" { print $2 }' "$conf" | tr -d '"' | tail -1)"
    file="$(awk '$1 == "dbfilename" { print $2 }' "$conf" | tr -d '"' | tail -1)"
    case "$dir" in /*) ;; *) fail "Redis's dir in $conf is '$dir', not an absolute path" ;; esac
    echo "$dir/${file:-dump.rdb}"
}
# Fail unless $DEST has room for directory $1, naming the flag ($2) that avoids it.
need_room() {
    local need_kb free_kb
    need_kb=$(du -sk "$1" | cut -f1)
    free_kb=$(df -Pk "$DEST" | awk 'NR==2 {print $4}')
    [ "$free_kb" -gt "$need_kb" ] || fail "not enough space in $DEST for $1 ($((need_kb/1024)) MB needed, $((free_kb/1024)) MB free); use --dest${2:+ or $2}"
}

[ "$(id -u)" -eq 0 ] || fail "run as root (it reads files only root can read)"

# --- Where Hop3 lives -------------------------------------------------------
# /etc/default/hop3 is what the service reads; HOP3_ROOT and HOP3_DATABASE_URI
# may be set there. Read it without sourcing (it is not trusted shell).
ENV_FILE=/etc/default/hop3
env_value() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 || true; }
HOP3_ROOT="${HOP3_ROOT:-$(env_value HOP3_ROOT)}"
HOP3_ROOT="${HOP3_ROOT:-/home/hop3}"
DB_URI="${HOP3_DATABASE_URI:-$(env_value HOP3_DATABASE_URI)}"
VENV="$HOP3_ROOT/venv"
PY="$VENV/bin/python"
HOP3_SERVER="$VENV/bin/hop3-server"

[ -d "$HOP3_ROOT" ] || fail "no Hop3 root at $HOP3_ROOT (set HOP3_ROOT if it lives elsewhere)"
[ -x "$PY" ] || fail "no server venv at $VENV"

HOST="$(hostname -s 2>/dev/null || hostname)"
STAMP="$(date +%Y%m%d-%H%M%S)"
LABEL="${LABEL:-$STAMP}"
DEST="${DEST:-/var/backups/hop3/${HOST}-${LABEL}}"
[ -e "$DEST" ] && fail "$DEST already exists; pick another --label or --dest"
mkdir -p "$DEST" && chmod 700 "$DEST"
echo "Hop3 server snapshot -> $DEST"

# --- 1. Versions and state, so the snapshot says what it is a snapshot of -----
echo "[1/6] versions and state"
{
    echo "host: $(hostname -f 2>/dev/null || hostname)"
    echo "date: $(date -Is)"
    echo "hop3_root: $HOP3_ROOT"
    echo "database_uri: ${DB_URI:-sqlite:///$HOP3_ROOT/hop3.db (default)}"
    for pkg in hop3_server hop3_rootd hop3_cli; do
        printf '%s: ' "$pkg"
        "$PY" -c "import importlib.metadata as m; print(m.version('$pkg'))" 2>/dev/null || echo "not installed"
    done
    printf 'schema: '
    sudo -u hop3 "$HOP3_SERVER" db:current 2>/dev/null | tail -1 || echo "unknown"
    echo "os: $(. /etc/os-release && echo "$PRETTY_NAME")"
    echo "python: $("$PY" --version 2>&1)"
} > "$DEST/versions.txt"
"$VENV/bin/pip" freeze > "$DEST/pip-freeze.txt" 2>/dev/null || true
if command -v dpkg-query >/dev/null; then
    dpkg-query -W -f '${Package} ${Version}\n' 2>/dev/null | grep -E '^(nginx|uwsgi|postgresql|mariadb-server|mysql-server|redis-server|docker\.io|nix)' > "$DEST/system-packages.txt" || true
elif command -v rpm >/dev/null; then
    rpm -qa 'nginx*' 'postgresql*' 'mariadb*' 'redis*' 'docker*' > "$DEST/system-packages.txt" 2>/dev/null || true
fi
if command -v systemctl >/dev/null && [ -d /run/systemd/system ]; then
    systemctl list-units --all --no-pager --plain 'hop3-*' 'uwsgi-hop3*' 'nginx*' 'postgresql*' 'mariadb*' 'mysql*' 'redis*' 'docker*' > "$DEST/services.txt" 2>/dev/null || true
else
    echo "no systemd on this host" > "$DEST/services.txt"
fi
"$PY" - "$HOP3_ROOT" "$DEST/apps.txt" <<'EOF' 2>/dev/null || echo "app list unavailable (non-SQLite database or old schema)" > "$DEST/apps.txt"
import sqlite3, sys
root, out = sys.argv[1], sys.argv[2]
con = sqlite3.connect(f"file:{root}/hop3.db?mode=ro", uri=True)
rows = con.execute("select name, run_state, coalesce(hostname,'') from app order by name").fetchall()
with open(out, "w") as f:
    for name, state, host in rows:
        f.write(f"{name}\t{state}\t{host}\n")
EOF
ok "versions.txt, pip-freeze.txt, services.txt, apps.txt ($(wc -l < "$DEST/apps.txt") apps)"

# --- 2. The control-plane database ------------------------------------------
echo "[2/6] control-plane database"
case "${DB_URI:-sqlite}" in
    sqlite*|"")
        SQLITE_PATH="$HOP3_ROOT/hop3.db"
        case "$DB_URI" in sqlite:////*) SQLITE_PATH="${DB_URI#sqlite:///}" ;; esac
        [ -f "$SQLITE_PATH" ] || fail "SQLite database not found at $SQLITE_PATH"
        # The backup API copies a consistent image while the server keeps running.
        "$PY" - "$SQLITE_PATH" "$DEST/hop3.db" <<'EOF'
import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.execute("pragma integrity_check").fetchone()[0] == "ok" or sys.exit("integrity check failed on the copy")
EOF
        ok "hop3.db ($(du -h "$DEST/hop3.db" | cut -f1), integrity checked)"
        ;;
    postgres*)
        command -v pg_dump >/dev/null || fail "HOP3_DATABASE_URI is PostgreSQL but pg_dump is not installed"
        pg_dump --no-owner "$DB_URI" | gzip > "$DEST/hop3-db.sql.gz" || fail "pg_dump of the control-plane database failed"
        ok "hop3-db.sql.gz (PostgreSQL)"
        ;;
    *) fail "unsupported HOP3_DATABASE_URI: $DB_URI" ;;
esac

# --- 3. Config, secrets, units, proxy and uWSGI trees -------------------------
echo "[3/6] config, secrets and service trees"
CONF_LIST="$DEST/config-files.txt"; : > "$CONF_LIST"
for path in \
    "$ENV_FILE" /etc/hop3 \
    "$HOP3_ROOT/hop3-server.toml" "$HOP3_ROOT/addons" "$HOP3_ROOT/.ssh/authorized_keys" \
    "$HOP3_ROOT/nginx" "$HOP3_ROOT/uwsgi" "$HOP3_ROOT/uwsgi-available" "$HOP3_ROOT/uwsgi-enabled" \
    "$HOP3_ROOT/caddy" "$HOP3_ROOT/traefik" "$HOP3_ROOT/catalog-state" \
    /etc/nginx/nginx.conf /etc/nginx/sites-available/hop3 /etc/nginx/conf.d /etc/letsencrypt \
    /etc/systemd/system/hop3-server.service /etc/systemd/system/hop3-rootd.service \
    /etc/systemd/system/hop3-rootd.socket /etc/systemd/system/uwsgi-hop3.service \
    /etc/garage.toml /etc/systemd/system/garage.service \
    /etc/supervisor/conf.d /etc/nix/nix.conf; do
    [ -e "$path" ] && echo "$path" >> "$CONF_LIST"
done
[ -s "$CONF_LIST" ] || fail "found none of the expected config files under $HOP3_ROOT and /etc"
tar czf "$DEST/config.tar.gz" --absolute-names -T "$CONF_LIST" 2>/dev/null || fail "archiving the config files"
ok "config.tar.gz ($(wc -l < "$CONF_LIST") paths; list in config-files.txt)"

# --- 4. The apps tree ---------------------------------------------------------
echo "[4/6] apps tree"
if [ "$SKIP_APPS" -eq 1 ]; then
    skip "apps tree (--skip-apps)"
elif [ ! -d "$HOP3_ROOT/apps" ]; then
    skip "no apps tree at $HOP3_ROOT/apps"
else
    need_room "$HOP3_ROOT/apps" --skip-apps
    tar czf "$DEST/apps.tar.gz" -C "$HOP3_ROOT" apps || fail "archiving $HOP3_ROOT/apps"
    ok "apps.tar.gz ($(du -h "$DEST/apps.tar.gz" | cut -f1))"
fi

# --- 5. Backing services ------------------------------------------------------
echo "[5/6] backing services"
# A database that runs and does not answer stops the backup; a stopped one is
# named, since its databases are then missing from the snapshot.
if ! command -v pg_dumpall >/dev/null; then
    skip "PostgreSQL (not installed)"
elif timeout 30 sudo -u postgres psql -Atqc 'select 1' >/dev/null 2>&1; then
    sudo -u postgres pg_dumpall --clean --if-exists | gzip > "$DEST/postgres-all.sql.gz" || fail "pg_dumpall"
    ok "postgres-all.sql.gz ($(sudo -u postgres psql -Atqc "select count(*) from pg_database where not datistemplate") databases)"
elif pgrep -x postgres >/dev/null; then
    fail "PostgreSQL is running but not answering (sudo -u postgres psql -c 'select 1')"
else
    skip "PostgreSQL is stopped: its databases are NOT in this snapshot; start it and re-run to include them"
fi
if ! command -v mysqldump >/dev/null; then
    skip "MySQL/MariaDB (not installed)"
elif timeout 30 mysql -e 'select 1' >/dev/null 2>&1; then
    mysqldump --all-databases --single-transaction --routines --events --triggers | gzip > "$DEST/mysql-all.sql.gz" || fail "mysqldump"
    ok "mysql-all.sql.gz"
elif pgrep -x 'mysqld|mariadbd' >/dev/null; then
    fail "MySQL/MariaDB is running but refuses root's socket login (mysql -e 'select 1')"
else
    skip "MySQL/MariaDB is not running (or only its client is installed): no MySQL databases in this snapshot"
fi
if command -v redis-cli >/dev/null; then
    REDIS_AUTH=()
    [ -s /etc/hop3/redis-pass ] && REDIS_AUTH=(-a "$(cat /etc/hop3/redis-pass)" --no-auth-warning)
    if timeout 10 redis-cli "${REDIS_AUTH[@]}" ping 2>/dev/null | grep -q PONG; then
        redis-cli "${REDIS_AUTH[@]}" --rdb "$DEST/redis-dump.rdb" >/dev/null 2>&1 || fail "redis-cli --rdb"
        ok "redis-dump.rdb"
    elif pgrep -x redis-server >/dev/null; then
        fail "Redis is running but not answering (redis-cli ping); it may save at any moment, so its dump cannot be copied"
    else
        # Stopped: its last save is at rest and copied as it is.
        REDIS_DUMP="$(redis_dump_path)"
        if [ -f "$REDIS_DUMP" ]; then
            cp -p "$REDIS_DUMP" "$DEST/redis-dump.rdb" || fail "copying $REDIS_DUMP"
            ok "redis-dump.rdb (Redis is stopped: its last save, $(date -r "$REDIS_DUMP" '+%F %T'))"
        else
            skip "Redis is stopped and has never saved ($REDIS_DUMP is missing): it holds no data"
        fi
    fi
else
    skip "Redis (not installed)"
fi
GARAGE_CONF=/etc/garage.toml
GARAGE_DIR=/var/lib/garage
SNAPSHOTS="$GARAGE_DIR/meta/snapshots"
if [ -f "$GARAGE_CONF" ]; then
    command -v garage >/dev/null || fail "Garage is configured ($GARAGE_CONF) but the garage binary is not on PATH"
    [ -d "$GARAGE_DIR" ] || fail "Garage is configured but its data directory $GARAGE_DIR is missing"
    need_room "$GARAGE_DIR"
    if garage -c "$GARAGE_CONF" status >/dev/null 2>&1; then
        # The metadata is a live SQLite database, so Garage writes a consistent
        # copy of it. Data blocks never change once written; archiving them
        # after the copy means every block the copy refers to is there.
        BEFORE=""
        [ -d "$SNAPSHOTS" ] && BEFORE="$(ls -1 "$SNAPSHOTS" | tail -1)"
        garage -c "$GARAGE_CONF" meta snapshot >/dev/null 2>&1 || fail "garage meta snapshot"
        SNAP="$(ls -1 "$SNAPSHOTS" | tail -1)"
        [ -n "$SNAP" ] && [ "$SNAP" != "$BEFORE" ] || fail "garage meta snapshot wrote no new snapshot in $SNAPSHOTS"
        cp "$SNAPSHOTS/$SNAP/db.sqlite" "$DEST/garage-meta.sqlite"
        rm -rf "${SNAPSHOTS:?}/$SNAP"
        tar czf "$DEST/garage.tar.gz" -C / --exclude='var/lib/garage/meta/db.sqlite*' \
            --exclude=var/lib/garage/meta/snapshots var/lib/garage || fail "archiving $GARAGE_DIR"
        ok "garage.tar.gz, garage-meta.sqlite ($(du -h "$DEST/garage.tar.gz" | cut -f1))"
    elif pgrep -x garage >/dev/null; then
        fail "Garage is running but not answering (garage -c $GARAGE_CONF status); its files are in use, so they cannot be copied"
    else
        # Stopped: its files are at rest and archived as they are.
        tar czf "$DEST/garage.tar.gz" -C / var/lib/garage || fail "archiving $GARAGE_DIR"
        ok "garage.tar.gz (Garage is stopped: archived at rest, $(du -h "$DEST/garage.tar.gz" | cut -f1))"
    fi
else
    skip "Garage (not installed)"
fi
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
    docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' > "$DEST/docker-containers.txt"
    docker volume ls --format '{{.Name}}' > "$DEST/docker-volumes.txt"
    if [ "$DOCKER_VOLUMES" -eq 1 ] && [ -s "$DEST/docker-volumes.txt" ]; then
        mkdir -p "$DEST/docker-volumes"
        while read -r vol; do
            docker run --rm -v "$vol":/v:ro -v "$DEST/docker-volumes":/out busybox \
                tar czf "/out/$vol.tar.gz" -C /v . || fail "archiving Docker volume $vol"
        done < "$DEST/docker-volumes.txt"
        ok "docker-volumes/ ($(wc -l < "$DEST/docker-volumes.txt") volumes)"
    else
        ok "docker-containers.txt, docker-volumes.txt (listed; volumes not archived, see --docker-volumes)"
    fi
else
    skip "Docker (not installed or daemon not running)"
fi

# --- 6. Manifest, checksums and restore notes ---------------------------------
echo "[6/6] manifest"
(cd "$DEST" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
cat > "$DEST/RESTORE.md" <<EOF
# Restoring from this snapshot

Taken $(date -Is) on $HOST, Hop3 root $HOP3_ROOT. Versions in versions.txt.

Platform rollback after a failed upgrade (apps untouched):

    systemctl stop hop3-server
    cp $DEST/hop3.db $HOP3_ROOT/hop3.db && chown hop3:hop3 $HOP3_ROOT/hop3.db   # SQLite; for PostgreSQL: gunzip -c hop3-db.sql.gz | psql "\$HOP3_DATABASE_URI"
    sudo -u hop3 $VENV/bin/pip install hop3-server==<previous> hop3-rootd==<previous>
    systemctl restart hop3-rootd.socket hop3-rootd.service hop3-server

Config and secrets: tar xzf config.tar.gz -C / (paths are absolute; see config-files.txt).
Apps tree: tar xzf apps.tar.gz -C $HOP3_ROOT (then systemctl restart uwsgi-hop3).
PostgreSQL: gunzip -c postgres-all.sql.gz | sudo -u postgres psql
MySQL: gunzip -c mysql-all.sql.gz | mysql
Garage (S3): systemctl stop garage; tar xzf garage.tar.gz -C /; if garage-meta.sqlite is here, cp it to /var/lib/garage/meta/db.sqlite and remove db.sqlite-wal and db.sqlite-shm there; systemctl start garage
Redis: systemctl stop redis-server; cp redis-dump.rdb <redis dir>/dump.rdb; chown redis:redis; systemctl start redis-server
Docker volumes: docker run --rm -v <vol>:/v -v $DEST/docker-volumes:/in busybox tar xzf /in/<vol>.tar.gz -C /v

Verify a file before using it: (cd $DEST && sha256sum -c SHA256SUMS)
EOF
ok "SHA256SUMS, RESTORE.md"
echo
echo "Snapshot complete: $DEST ($(du -sh "$DEST" | cut -f1))"
