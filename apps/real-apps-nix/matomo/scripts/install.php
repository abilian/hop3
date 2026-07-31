<?php
/*
 * Install Matomo headlessly (Hop3 ADR 056).
 *
 * Matomo 5 ships no console command for installation or for creating a
 * superuser: its Installation plugin is a browser wizard (Controller.php +
 * Form* classes), which a deploy cannot click through. So this bootstraps
 * Matomo exactly as ./console does, then performs the same steps that wizard
 * performs:
 *
 *   DbHelper::createTables()         - the schema           (Controller.php:217)
 *   DbHelper::createAnonymousUser()  - the anonymous user         (:218)
 *   DbHelper::recordInstallVersion() - the install marker         (:219)
 *   a superuser                                                   (:700)
 *   a first site
 *
 * The superuser is created through UsersManager's MODEL rather than its API.
 * The API path renders an invitation email, which pulls in the theme and asset
 * manager and dies under the CLI ("Call to a member function getThemeName() on
 * null"). The model writes the same row; the password goes through the same two
 * stages the API uses (UsersManager::getPasswordHash then Auth\Password::hash),
 * so the stored credential is byte-identical to one the web UI would produce.
 *
 * Each step is guarded separately, so this is idempotent AND resumable: a run
 * that created the schema and then failed will, on the next deploy, skip the
 * schema and go on to create the superuser. Checking only "do tables exist?"
 * would declare a half-installed database finished and leave an app nobody can
 * log into. An existing superuser is never touched, so a redeploy cannot reset
 * an operator's password.
 */

if (php_sapi_name() !== 'cli') {
    fwrite(STDERR, "Matomo install: must run under the PHP CLI\n");
    exit(1);
}

define('PIWIK_DOCUMENT_ROOT', dirname(__DIR__));
define('PIWIK_INCLUDE_PATH', PIWIK_DOCUMENT_ROOT);
require_once PIWIK_INCLUDE_PATH . '/core/bootstrap.php';

use Piwik\Access;
use Piwik\Application\Environment;
use Piwik\Config;
use Piwik\Auth\Password;
use Piwik\Date;
use Piwik\DbHelper;
use Piwik\Plugins\SitesManager\API as SitesManagerAPI;
use Piwik\Plugins\UsersManager\Model as UsersModel;
use Piwik\Plugins\UsersManager\UsersManager;

/**
 * Tell Matomo it sits behind Hop3's TLS-terminating reverse proxy.
 *
 * Without this Matomo reads PHP's own view of the request, so it believes it is
 * on plain HTTP and redirects there after sign-in — and with HTTPS enforced at
 * the proxy that round trip drops the session, which presents as the app simply
 * refusing correct credentials.
 *
 * The client-IP header matters even more here than for a typical app: Matomo IS
 * an analytics tool, so without it every visit is attributed to the proxy
 * (127.0.0.1) rather than the real visitor, and its per-IP brute-force lockout
 * would lock out every user at once.
 *
 * Applied on every deploy, not just at install: these values follow the
 * platform, not operator preference, so an instance installed before this
 * existed is repaired on its next deploy. Written through Matomo's own Config
 * API so the rest of config.ini.php is preserved.
 */
function configureForReverseProxy(): void
{
    $config = Config::getInstance();
    $general = $config->General;

    $desired = [
        'proxy_client_headers' => ['HTTP_X_FORWARDED_FOR'],
        'proxy_host_headers' => ['HTTP_X_FORWARDED_HOST'],
        'assume_secure_protocol' => 1,
    ];

    $changed = false;
    foreach ($desired as $key => $value) {
        if (!isset($general[$key]) || $general[$key] != $value) {
            $general[$key] = $value;
            $changed = true;
        }
    }

    if ($changed) {
        $config->General = $general;
        $config->forceSave();
        echo "Matomo: configured for Hop3's reverse proxy (HTTPS + real client IP).\n";
    }
}

/**
 * Create Hop3's own probe account: a plain user, never a superuser.
 *
 * The [admin] credential is handed to the operator, so it stops being Hop3's to
 * assert the moment they change the password. This account is Hop3's alone, so
 * a refused sign-in means the app broke. Signing in is the entire diagnostic
 * value, hence no superuser access.
 *
 * Idempotent, and silent when no [probe] is declared.
 */
function createProbeUser(): void
{
    $login = getenv('HOP3_PROBE_USER');
    $password = getenv('HOP3_PROBE_PASSWORD');
    if (!$login || !$password) {
        return;
    }

    $model = new UsersModel();
    if ($model->getUser($login)) {
        return;
    }

    // Same two stages the API uses, so the stored credential is byte-identical
    // to one the web UI would produce.
    $hashed = (new Password())->hash(UsersManager::getPasswordHash($password));
    $email = getenv('HOP3_PROBE_EMAIL') ?: $login . '@hop3.invalid';
    $model->addUser($login, $hashed, $email, Date::now()->getDatetime());
    echo "Matomo probe user '{$login}' created.\n";
}

/**
 * Give the probe VIEW access to every site — read-only, still not a superuser.
 *
 * An account with no access authenticates perfectly and can reach nothing: the
 * sign-in POST returns 302 and sets MATOMO_SESSID, and the very next request
 * for a report page returns 403 rendering "Sign in - Matomo". Measured, not
 * assumed. To anything reading the response that is indistinguishable from a
 * refused password, and it is exactly what the smoke test reported.
 *
 * View on one site is the smallest access that makes a session observable, and
 * it is what a real Matomo account has — an account with none is a degenerate
 * case the application is not written for. Superuser it is still not.
 *
 * Separate from creation because the site does not exist yet when the probe is
 * made: the installer adds the first site afterwards. Idempotent — access rows
 * are inserted only for sites the probe does not already hold.
 */
function grantProbeSiteAccess(): void
{
    $login = getenv('HOP3_PROBE_USER');
    if (!$login) {
        return;
    }

    $model = new UsersModel();
    if (!$model->getUser($login)) {
        return;
    }

    $held = [];
    foreach ($model->getSitesAccessFromUser($login) as $row) {
        $held[(int) $row['site']] = true;
    }

    $missing = [];
    Access::doAsSuperUser(function () use (&$missing, $held) {
        foreach (SitesManagerAPI::getInstance()->getAllSites() as $site) {
            $idSite = (int) $site['idsite'];
            if (!isset($held[$idSite])) {
                $missing[] = $idSite;
            }
        }
    });

    if (!$missing) {
        return;
    }
    $model->addUserAccess($login, 'view', $missing);
    echo "Matomo probe user '{$login}' granted view access to site(s) "
        . implode(', ', $missing) . ".\n";
}

function envOrFail(string $name): string
{
    $value = getenv($name);
    if ($value === false || $value === '') {
        fwrite(STDERR, "Matomo install: {$name} not set (declare it under [admin] in hop3.toml)\n");
        exit(1);
    }
    return $value;
}

// [probe].create — the command Hop3 runs, and whose exit code it believes.
//
// Matomo ships no user CLI, so the probe account is made through the same model
// calls as the full install. It is a separate entry point rather than a side
// effect of installing, because Hop3 has to be able to invoke it on its own and
// watch it succeed: a probe it cannot create is a probe it cannot offer to the
// smoke test, which is how this app's [probe] section came to be decoration.
if (in_array('--probe-only', $argv, true)) {
    try {
        $environment = new Environment(null);
        $environment->init();
        configureForReverseProxy();

        $probeLogin = envOrFail('HOP3_PROBE_USER');
        createProbeUser();
        grantProbeSiteAccess();

        // Verify, do not assume — and verify what the smoke test actually needs.
        // Existence alone was not enough: the account existed, signed in, and
        // still could not open a single page.
        $probeModel = new UsersModel();
        if (!$probeModel->getUser($probeLogin)) {
            fwrite(STDERR, "Matomo probe: user '{$probeLogin}' absent after create\n");
            exit(1);
        }
        if (!$probeModel->getSitesAccessFromUser($probeLogin)) {
            fwrite(STDERR, "Matomo probe: '{$probeLogin}' can reach no site, so a "
                . "signed-in page would 403 and read as a refused password\n");
            exit(1);
        }
        exit(0);
    } catch (Throwable $e) {
        fwrite(STDERR, 'Matomo probe failed: ' . $e->getMessage() . "\n");
        exit(1);
    }
}

$login = envOrFail('HOP3_ADMIN_USER');
$password = envOrFail('HOP3_ADMIN_PASSWORD');
$email = envOrFail('HOP3_ADMIN_EMAIL');
$siteUrl = getenv('HOP3_PUBLIC_URL') ?: 'http://localhost';
$siteName = getenv('APP') ?: 'Matomo';

try {
    $environment = new Environment(null);
    $environment->init();

    configureForReverseProxy();

    if (empty(DbHelper::getTablesInstalled())) {
        DbHelper::createTables();
        DbHelper::createAnonymousUser();
        DbHelper::recordInstallVersion();
        echo "Matomo: schema created.\n";
    } else {
        echo "Matomo: schema already present.\n";
    }

    $model = new UsersModel();

    if (empty($model->getUsersHavingSuperUserAccess())) {
        // Same two stages as UsersManager\API::addUser (API.php:916, :923).
        $hashed = (new Password())->hash(UsersManager::getPasswordHash($password));
        $model->addUser($login, $hashed, $email, Date::now()->getDatetime());
        $model->setSuperUserAccess($login, true);
        echo "Matomo: superuser '{$login}' created.\n";
    } else {
        // NO exit() here. This branch used to return outright, which skipped
        // both the probe account below and the site creation after it — so any
        // instance that already had a superuser silently got neither, and the
        // smoke test then failed against a probe nobody had created.
        echo "Matomo: a superuser already exists; leaving it untouched.\n";
    }

    createProbeUser();

    // Matomo keeps prompting for setup until at least one site exists, so the
    // app would be installed but still not usable without this.
    Access::doAsSuperUser(function () use ($siteName, $siteUrl) {
        if (empty(SitesManagerAPI::getInstance()->getAllSites())) {
            SitesManagerAPI::getInstance()->addSite($siteName, [$siteUrl]);
        }
    });

    // After the site exists — the probe has nothing to be granted access to
    // before this point.
    grantProbeSiteAccess();

    echo "Matomo installed.\n";
    exit(0);
} catch (Throwable $e) {
    fwrite(STDERR, 'Matomo install failed: ' . $e->getMessage() . "\n");
    exit(1);
}
