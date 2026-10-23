#!/bin/bash
# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
#
# Put a Hop3 server back the way a snapshot from hop3-server-backup.sh had it:
# the control-plane database, every config and secret file, the apps tree, and
# each backing service the snapshot holds a dump of. Runs as root on the
# server. It stops hop3-server and the app processes while it works, restores
# the pieces the snapshot has (or only those named with --only), migrates the
# restored database forward to the installed code, and starts everything
# again, refusing to report success unless the server answers.
#
# Usage (on the server, as root):
#   hop3-server-restore.sh SNAPSHOT_DIR --yes [--only db,config,apps,postgres,mysql,redis,garage,docker-volumes]
#
# Every replaced file keeps a copy beside it, suffixed .pre-restore-<stamp>,
# so a restore that turns out to be the wrong one can itself be undone.
# A snapshot from a NEWER Hop3 than the installed one is refused: install that
# release first, then restore. An older snapshot is fine; its schema is
# migrated forward after it is put in place.

set -euo pipefail

SNAPSHOT=""
YES=0
ONLY=""

while [ $# -gt 0 ]; do
    case "$1" in
        --yes) YES=1; shift ;;
        --only) ONLY="$2"; shift 2 ;;
        -h|--help) sed -n '5,20p' "$0"; exit 0 ;;
        -*) echo "unknown option: $1" >&2; exit 2 ;;
        *) SNAPSHOT="$1"; shift ;;
    esac
done

ok()   { printf '  ok    %s\n' "$*"; }
skip() { printf '  skip  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run as root"
[ -n "$SNAPSHOT" ] || fail "usage: hop3-server-restore.sh SNAPSHOT_DIR --yes [--only ...]"
[ -d "$SNAPSHOT" ] || fail "no snapshot directory at $SNAPSHOT"
[ "$YES" -eq 1 ] || fail "this replaces the server's state with $SNAPSHOT; pass --yes to proceed"

# --- The snapshot, and whether this box can take it ------------------------
echo "[1/5] checking $SNAPSHOT"
(cd "$SNAPSHOT" && sha256sum --quiet -c SHA256SUMS) || fail "checksums do not match: the snapshot is damaged or incomplete"
SNAP_ROOT="$(sed -n 's/^hop3_root: //p' "$SNAPSHOT/versions.txt")"
SNAP_VERSION="$(sed -n 's/^hop3_server: //p' "$SNAPSHOT/versions.txt")"
HOP3_ROOT="${HOP3_ROOT:-${SNAP_ROOT:-/home/hop3}}"
VENV="$HOP3_ROOT/venv"
PY="$VENV/bin/python"
[ -x "$PY" ] || fail "no Hop3 installed at $HOP3_ROOT; install it first, then restore"
INSTALLED="$("$PY" -c 'import importlib.metadata as m; print(m.version("hop3_server"))' 2>/dev/null || true)"
[ -n "$INSTALLED" ] || fail "cannot read the installed hop3-server version from $VENV"
NEWEST="$(printf '%s\n%s\n' "$SNAP_VERSION" "$INSTALLED" | sort -V | tail -1)"
if [ "$SNAP_VERSION" != "$INSTALLED" ] && [ "$NEWEST" = "$SNAP_VERSION" ]; then
    fail "the snapshot was taken on hop3-server $SNAP_VERSION and this box runs $INSTALLED; install $SNAP_VERSION or newer first"
fi
ok "checksums verified; snapshot from hop3-server ${SNAP_VERSION:-?}, box runs $INSTALLED"

has()  { [ -e "$SNAPSHOT/$1" ]; }
want() {
    # Component $1 is in scope when --only names it (or --only is absent) and
    # the snapshot holds it.
    case ",$ONLY," in
        ",,") ;;
        *",$1,"*) ;;
        *) return 1 ;;
    esac
    case "$1" in
        db) has hop3.db || has hop3-db.sql.gz ;;
        config) has config.tar.gz ;;
        apps) has apps.tar.gz ;;
        postgres) has postgres-all.sql.gz ;;
        mysql) has mysql-all.sql.gz ;;
        redis) has redis-dump.rdb ;;
        garage) has garage.tar.gz ;;
        docker-volumes) has docker-volumes ;;
        *) fail "unknown component in --only: $1" ;;
    esac
}
for c in ${ONLY//,/ }; do want "$c" || fail "--only names '$c' but the snapshot does not hold it"; done

# --- Process manager ---------------------------------------------------------
# The emperor is `uwsgi-hop3` under both: the systemd unit, and the supervisor
# program named after it.
UWSGI_SVC=uwsgi-hop3
if [ "$(cat /proc/1/comm 2>/dev/null)" = "systemd" ]; then
    PM=systemd
else
    PM=supervisor
    command -v supervisorctl >/dev/null || fail "neither systemd nor supervisorctl found; cannot manage services"
fi
svc_stop() {
    if [ "$PM" = systemd ]; then systemctl stop "$1" 2>/dev/null || true
    else supervisorctl stop "$1" >/dev/null 2>&1 || true; fi
}
svc_start() {
    if [ "$PM" = systemd ]; then systemctl start "$1"
    else supervisorctl start "$1" >/dev/null 2>&1 || supervisorctl status "$1" | grep -q RUNNING; fi
}
svc_restart() {
    # Best effort for services the box may not manage (rootd, nginx on a
    # container); the server check at the end is what decides success.
    if [ "$PM" = systemd ]; then systemctl restart "$1" 2>/dev/null || return 1
    else supervisorctl restart "$1" >/dev/null 2>&1 || return 1; fi
}

STAMP="$(date +%Y%m%d-%H%M%S)"
echo "[2/5] stopping services"
svc_stop hop3-server && ok "hop3-server stopped"
STOPPED_APPS=0
if want apps || want db || want postgres || want mysql || want redis || want garage; then
    svc_stop "$UWSGI_SVC" && ok "app processes stopped ($UWSGI_SVC)"
    STOPPED_APPS=1
fi

# --- Restore ---------------------------------------------------------------
echo "[3/5] restoring"
if want config; then
    # Absolute paths inside (hop3-server-backup.sh archives with --absolute-names).
    tar xzPf "$SNAPSHOT/config.tar.gz" -C / || fail "extracting config.tar.gz"
    [ "$PM" = systemd ] && systemctl daemon-reload
    ok "config, secrets and service trees ($(wc -l < "$SNAPSHOT/config-files.txt") paths)"
else
    skip "config"
fi

if want db; then
    if has hop3.db; then
        DB="$HOP3_ROOT/hop3.db"
        [ -f "$DB" ] && mv "$DB" "$DB.pre-restore-$STAMP"
        cp "$SNAPSHOT/hop3.db" "$DB" && chown hop3:hop3 "$DB" && chmod 0640 "$DB"
        rm -f "$DB-wal" "$DB-shm"
        ok "control-plane database (previous kept as $DB.pre-restore-$STAMP)"
    else
        fail "the snapshot holds a PostgreSQL control-plane dump (hop3-db.sql.gz); restoring it is not automated: gunzip -c hop3-db.sql.gz | psql \"\$HOP3_DATABASE_URI\", then re-run with --only for the rest"
    fi
else
    skip "control-plane database"
fi

if want apps; then
    APPS="$HOP3_ROOT/apps"
    [ -d "$APPS" ] && mv "$APPS" "$APPS.pre-restore-$STAMP"
    tar xzf "$SNAPSHOT/apps.tar.gz" -C "$HOP3_ROOT" || fail "extracting apps.tar.gz"
    chown -R hop3:hop3 "$APPS"
    ok "apps tree (previous kept as $APPS.pre-restore-$STAMP)"
else
    skip "apps tree"
fi

if want postgres; then
    sudo -u postgres psql -Atqc 'select 1' >/dev/null 2>&1 || fail "PostgreSQL is not answering; start it, then re-run with --only postgres"
    # The dump drops and recreates each database; a lingering connection blocks that.
    sudo -u postgres psql -Atqc "select pg_terminate_backend(pid) from pg_stat_activity where pid <> pg_backend_pid() and datname is not null" >/dev/null
    # `pg_dumpall --clean` also emits DROP ROLE and CREATE ROLE for the
    # bootstrap superuser, and the restoring session runs as that user, so
    # PostgreSQL refuses the drop ("current user cannot be dropped") and then
    # the create ("already exists"), and ON_ERROR_STOP would end the restore
    # there. Those two statements are skipped (its ALTER ROLE still applies);
    # every other error still stops the restore.
    gunzip -c "$SNAPSHOT/postgres-all.sql.gz" \
        | grep -v -E '^(DROP ROLE IF EXISTS|CREATE ROLE) "?postgres"?;$' \
        | sudo -u postgres psql -q -v ON_ERROR_STOP=1 -f - >/dev/null || fail "restoring the PostgreSQL dump"
    ok "PostgreSQL ($(sudo -u postgres psql -Atqc "select count(*) from pg_database where not datistemplate") databases)"
else
    skip "PostgreSQL"
fi

if want mysql; then
    mysql -e 'select 1' >/dev/null 2>&1 || fail "MySQL is not answering as root; start it, then re-run with --only mysql"
    gunzip -c "$SNAPSHOT/mysql-all.sql.gz" | mysql || fail "restoring the MySQL dump"
    ok "MySQL"
else
    skip "MySQL"
fi

if want redis; then
    command -v redis-cli >/dev/null || fail "redis-cli not installed; cannot restore the Redis dump"
    REDIS_AUTH=()
    [ -s /etc/hop3/redis-pass ] && REDIS_AUTH=(-a "$(cat /etc/hop3/redis-pass)" --no-auth-warning)
    REDIS_DIR="$(redis-cli "${REDIS_AUTH[@]}" CONFIG GET dir 2>/dev/null | sed -n 2p)"
    [ -n "$REDIS_DIR" ] || fail "Redis is not answering; cannot find its data directory"
    svc_stop redis-server
    cp "$SNAPSHOT/redis-dump.rdb" "$REDIS_DIR/dump.rdb" && chown redis:redis "$REDIS_DIR/dump.rdb"
    svc_start redis-server || fail "Redis did not start after the restore"
    ok "Redis"
else
    skip "Redis"
fi

if want garage; then
    command -v garage >/dev/null || fail "Garage is not installed; install the server with --with s3, then re-run with --only garage"
    GARAGE_DIR=/var/lib/garage
    svc_stop garage
    [ -d "$GARAGE_DIR" ] && mv "$GARAGE_DIR" "$GARAGE_DIR.pre-restore-$STAMP"
    tar xzf "$SNAPSHOT/garage.tar.gz" -C / || fail "extracting garage.tar.gz"
    if has garage-meta.sqlite; then
        # A snapshot of a running Garage holds its metadata as a consistent copy.
        cp "$SNAPSHOT/garage-meta.sqlite" "$GARAGE_DIR/meta/db.sqlite"
        rm -f "$GARAGE_DIR/meta/db.sqlite-wal" "$GARAGE_DIR/meta/db.sqlite-shm"
    fi
    svc_start garage || fail "Garage did not start after the restore"
    for _ in $(seq 1 15); do
        garage -c /etc/garage.toml status >/dev/null 2>&1 && break
        sleep 2
    done
    garage -c /etc/garage.toml status >/dev/null 2>&1 || fail "Garage did not answer within 30 s after the restore; the previous tree is at $GARAGE_DIR.pre-restore-$STAMP"
    ok "Garage (previous kept as $GARAGE_DIR.pre-restore-$STAMP)"
else
    skip "Garage"
fi

if want docker-volumes; then
    docker info >/dev/null 2>&1 || fail "Docker is not running; cannot restore its volumes"
    for archive in "$SNAPSHOT"/docker-volumes/*.tar.gz; do
        vol="$(basename "$archive" .tar.gz)"
        docker volume create "$vol" >/dev/null
        docker run --rm -v "$vol":/v -v "$SNAPSHOT/docker-volumes":/in:ro busybox \
            sh -c "rm -rf /v/* /v/.[!.]* 2>/dev/null; tar xzf /in/$vol.tar.gz -C /v" || fail "restoring Docker volume $vol"
    done
    ok "Docker volumes ($(ls "$SNAPSHOT"/docker-volumes/*.tar.gz | wc -l))"
else
    skip "Docker volumes"
fi

# --- Bring the schema to the installed code, and everything back up ----------
echo "[4/5] migrating the restored database to hop3-server $INSTALLED"
if want db; then
    sudo -u hop3 "$VENV/bin/hop3-server" db:upgrade >/dev/null || fail "db:upgrade failed after the restore; the previous database is at $HOP3_ROOT/hop3.db.pre-restore-$STAMP"
    ok "schema at $(sudo -u hop3 "$VENV/bin/hop3-server" db:current 2>/dev/null | tail -1)"
else
    skip "migration (database not restored)"
fi

echo "[5/5] starting services"
svc_restart hop3-rootd && ok "hop3-rootd restarted" || skip "hop3-rootd (not managed here)"
svc_restart nginx && ok "nginx restarted" || skip "nginx (not managed here)"
if [ "$STOPPED_APPS" -eq 1 ]; then
    svc_start "$UWSGI_SVC" || fail "$UWSGI_SVC did not start"
    ok "app processes started"
fi
svc_start hop3-server || fail "hop3-server did not start"
for _ in $(seq 1 30); do
    if curl -s -o /dev/null -m 3 http://127.0.0.1:8000/; then
        ok "hop3-server answers"
        echo
        echo "Restore complete from $SNAPSHOT"
        exit 0
    fi
    sleep 2
done
fail "hop3-server did not answer within 60 s; see $([ "$PM" = systemd ] && echo 'journalctl -u hop3-server -n 100' || echo 'supervisorctl tail -100 hop3-server')"
