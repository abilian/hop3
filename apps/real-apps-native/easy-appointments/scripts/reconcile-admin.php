<?php
/**
 * Reconcile the Easy!Appointments seeded admin with Hop3's generated admin
 * credentials (ADR-056).
 *
 * `php index.php console install` creates the schema and seeds a fixed admin
 * ("administrator" / "administrator", john@example.org). The console has no way
 * to read injected credentials, so this script re-keys that seeded admin to the
 * HOP3_ADMIN_* values Hop3 generated and injected. It runs once, right after the
 * console install, inside setup-config.sh's "not installed" branch — so a
 * redeploy (schema already present) never re-runs it.
 *
 * Password hashing reuses Easy!Appointments' own hash_password()/generate_salt()
 * helpers (required below) so the stored hash always matches what the app's login
 * expects, with no duplicated crypto.
 */

// Minimal shims so the app's password helper loads standalone (outside
// CodeIgniter): the helper only guards on BASEPATH being defined, and uses the
// MAX_PASSWORD_LENGTH upper-bound constant.
define('BASEPATH', __DIR__);
if (!defined('MAX_PASSWORD_LENGTH')) {
    define('MAX_PASSWORD_LENGTH', 100);
}
require __DIR__ . '/../application/helpers/password_helper.php';

function fail(string $message): void
{
    fwrite(STDERR, 'Easy!Appointments admin reconcile failed: ' . $message . "\n");
    exit(1);
}

$username = getenv('EA_ADMIN_USERNAME');
$email = getenv('EA_ADMIN_EMAIL');
$password = getenv('EA_ADMIN_PASSWORD');

if ($username === false || $username === '') {
    fail('EA_ADMIN_USERNAME not set (expected from HOP3_ADMIN_USER)');
}
if ($email === false || $email === '') {
    fail('EA_ADMIN_EMAIL not set (expected from HOP3_ADMIN_EMAIL)');
}
if ($password === false || $password === '') {
    fail('EA_ADMIN_PASSWORD not set (expected from HOP3_ADMIN_PASSWORD)');
}

$host = getenv('MYSQL_HOST') ?: 'localhost';
$port = (int) (getenv('MYSQL_PORT') ?: 3306);
$database = getenv('MYSQL_DATABASE') ?: 'easyappointments';
$db_user = getenv('MYSQL_USER') ?: 'easyappointments';
$db_pass = getenv('MYSQL_PASSWORD') ?: '';

mysqli_report(MYSQLI_REPORT_OFF);
$db = @mysqli_connect($host, $db_user, $db_pass, $database, $port);
if (!$db) {
    fail('database connection failed: ' . mysqli_connect_error());
}

// Find the seeded administrator (role slug 'admin'); tables use the ea_ prefix.
$result = mysqli_query(
    $db,
    "SELECT u.id FROM ea_users u
       INNER JOIN ea_roles r ON u.id_roles = r.id
      WHERE r.slug = 'admin'
      ORDER BY u.id ASC
      LIMIT 1"
);
if (!$result) {
    fail('could not query admin user: ' . mysqli_error($db));
}
$row = mysqli_fetch_assoc($result);
if (!$row) {
    fail('no admin user found after console install');
}
$admin_id = (int) $row['id'];

$salt = generate_salt();
$hash = hash_password($salt, $password);

// Update the operator email on the users row.
$stmt = mysqli_prepare(
    $db,
    'UPDATE ea_users SET email = ?, update_datetime = NOW() WHERE id = ?'
);
if (!$stmt) {
    fail('prepare users update failed: ' . mysqli_error($db));
}
mysqli_stmt_bind_param($stmt, 'si', $email, $admin_id);
if (!mysqli_stmt_execute($stmt)) {
    fail('users update failed: ' . mysqli_stmt_error($stmt));
}
mysqli_stmt_close($stmt);

// Update the login credentials on the user_settings row.
$stmt = mysqli_prepare(
    $db,
    'UPDATE ea_user_settings SET username = ?, password = ?, salt = ? WHERE id_users = ?'
);
if (!$stmt) {
    fail('prepare user_settings update failed: ' . mysqli_error($db));
}
mysqli_stmt_bind_param($stmt, 'sssi', $username, $hash, $salt, $admin_id);
if (!mysqli_stmt_execute($stmt)) {
    fail('user_settings update failed: ' . mysqli_stmt_error($stmt));
}
if (mysqli_stmt_affected_rows($stmt) < 1) {
    fail('admin settings row not found (id_users=' . $admin_id . ')');
}
mysqli_stmt_close($stmt);

echo "Easy!Appointments admin reconciled to injected credentials (username: {$username})\n";
