#!/bin/bash
# Reset the seeded Kanboard admin password to the Hop3-generated one (ADR 056).
#
# Kanboard's schema (app/Schema/Mysql.php) seeds an 'admin'/'admin' account the
# first time `php cli db:migrate` builds the database. Shipping that default is a
# credential land-grab, so once migration has run we overwrite the admin password
# with the injected HOP3_ADMIN_PASSWORD. Kanboard has no password-reset CLI, so we
# bootstrap its own DI container and update the users table using Kanboard's own
# hashing (password_hash + PASSWORD_BCRYPT — the exact scheme used both in the
# schema seed and in UserModel::prepare).
#
# Idempotent: re-running simply re-applies the same (stable) password. Fail-loud:
# a missing password or an absent admin row aborts the deploy.

set -euo pipefail

: "${HOP3_ADMIN_PASSWORD:?HOP3_ADMIN_PASSWORD is required to reset the Kanboard admin password}"

php <<'PHP'
<?php
require getcwd() . '/app/common.php';

$password = getenv('HOP3_ADMIN_PASSWORD');
if ($password === false || $password === '') {
    fwrite(STDERR, "HOP3_ADMIN_PASSWORD is empty; refusing to reset the Kanboard admin password\n");
    exit(1);
}

$db = $container['db'];
$admin = $db->table('users')->eq('username', 'admin')->findOne();
if (empty($admin)) {
    fwrite(STDERR, "Kanboard 'admin' user not found; 'php cli db:migrate' must run first\n");
    exit(1);
}

$hash = password_hash($password, PASSWORD_BCRYPT);
$ok = $db->table('users')->eq('id', $admin['id'])->update(array('password' => $hash));
if ($ok === false) {
    fwrite(STDERR, "Failed to reset the Kanboard admin password\n");
    exit(1);
}

echo "Reset Kanboard admin password for user 'admin'\n";
PHP
