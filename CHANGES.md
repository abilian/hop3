# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Tutorial: your own Flask app, built hermetically by Nix** (`docs/tutorials/nix/nix-gen-flask.md`). No Nix code and no Nix on the reader's machine: a `[nix]` template, a hash-pinned lockfile, and a deploy.
- **The `catch` email backend has a sink: Mailpit.** `--with email` installs it, pinned by version and SHA-256, and runs it on loopback under the process manager. Selecting `catch` checks that it answers; it used to point Postfix at a port nothing listened on, report success, and leave every message deferred. `hop3 server email caught` lists the captured mail, and `server email status` now names the active backend, where it reported no transport for `catch` and `direct`. `hop3-test` selects `catch` for a run that includes an app declaring email, and the `190-flask-email` fixture checks the whole path: a message sent through the injected relay, found in the sink.

- **`[access]` puts an app behind a Hop3 sign-in.** With `require = "auth"`, a visitor without a session is sent to the sign-in on the admin domain and back to the page they asked for. `role` sets the lowest role admitted, and `public-paths` leaves webhooks and health checks open. The app learns who is asking from `X-Hop3-User` and `X-Hop3-Role`, which a client cannot forge, and never receives the gate's cookie. A sign-in link works only in the browser that started it, so nobody can sign a visitor in to their own account. One sign-in covers every gated app, and signing out of Hop3 signs out of all of them. Works on nginx, Caddy and Traefik. (ADR 062)

- **`[proxy] deny` lists paths the proxy answers with 404.** `deny = ["/data"]` refuses `/data` and everything beneath it before the app or the disk sees the request, and a PHP script there is refused rather than run. It is for data an app keeps inside the tree it serves, which upstream protects with an `.htaccess` that nginx and Caddy never read. Traefik cannot refuse a path, so a deploy that declares one is refused there.

- **A generated Nix recipe can fetch its source from GitHub by repository**: `github = "OWNER/REPO"`, `rev` and `hash` in `[nix]`. The hash is of the unpacked tree, which GitHub keeps stable, where the bytes of its generated archives change without notice; a `url` pointing at a GitHub `/archive/` link is now refused with the command that prints the hash.

- **`ruby-bundler` builds gems with a Rust extension.** `gem-cargo-hashes = { commonmarker = "sha256-…" }` in `[nix]` vendors the gem's crates before the offline build, which is what Redmine 6 needs.

- **A catalog entry can say which server it needs.** `requires_hop3 = "0.8"` in an entry's `catalog.toml` makes an older server refuse `hop3 catalog install` by name, before it creates anything, where it used to stage the recipe and fail in the middle of the build. The publisher now works out what a recipe needs from its `hop3.toml` (php-fpm, scratch volumes, `[proxy] deny`, `[access]`, a GitHub Nix source, and others) and from a hand-written `hop3.nix` (a setup step in `before_run`), records the feature names in the signed index, and refuses to publish a recipe whose `requires_hop3` is lower than those features need: Paheko, WordPress, Dolibarr and Kanboard needed php-fpm and did not say so. A server refuses an entry that names a feature it does not have.

- **Accounts have roles: `admin`, `deployer`, `viewer` and `member`.** `hop3 user set-role alice viewer` grants one; `hop3 user add --role` sets it at creation. A viewer reads apps, addons, backups and certificates but no secret. A deployer deploys and operates apps and addons. An admin also manages accounts and the server. A member signs in to the web interface and sees its own profile. A deployer's builds run with the control plane's own privileges, so treat that role as an administrator credential. (ADR 061)

- **`[[volumes]]` has a `scratch` type**, for directories an app writes that must not be kept: a framework's compiled templates or bootstrap cache. It lives outside `src/`, is reset to what the build leaves there whenever a deploy replaces `src/`, and is never backed up.

- **`hop3-test` installs the runtime the selected apps are built with.** A Nix-built app brings `--with nix` and a Docker-built one `--with docker`, as their addons already brought theirs, now that nothing is installed by default. On the Docker target, which cannot run Docker, Docker-built apps are left out before the deploy, each with the reason.

- **`hop3-test` fails a server deploy that carried past a warning.** Each ⚠ line the installer or the deployer prints fails the run, unless an allowlist entry says why it is safe to continue. Every run log carried such lines for weeks, two bugs and an install that failed on every Ubuntu 24.04 server among them, and nobody read them.

- **`hop3-test` fails an app that writes into `src/` while running, and redeploys every app.** Each deploy replaces `src/`, so whatever an app writes there is lost at the next one, an upgrade included. The test lists the directories the app wrote to after it started, grouped for a `[[volumes]]` entry. It then deploys the unchanged source again and runs every validation a second time. `--no-redeploy` skips the second deploy.

### Changed

- **`hop3 context use --global <name>` sets the default target, and `hop3 login --context <name>` signs in again without a target.** Only a login could change the global default context, and `hop3 login --context dev` asked for a username and password, though `dev` recorded an SSH address. `context use` now sets the global default with `--global`, or when run outside a project, and says when the environment outranks it. A login that names a context and no target signs in over the SSH route the context records; `--username` still asks for the password form.
- **The catalog is fetched from a path that names its format**: `https://apps.hop3.cloud/catalog/v1/catalog.tar.gz`. The server reads the `format` the signed index declares and refuses one it does not know, naming it and keeping the catalog it holds; the publisher had written `"format": 1` since the catalog shipped, and no server read it. A future format is published beside this one, under `v2/`, so a server that reads only format 1 keeps receiving updates. Servers before 0.8 keep fetching the old path, which carries the same catalog. A `CATALOG_SOURCE_URL` set to the old path still works; move it to `v1/`.

- **The deploy that first declares a volume keeps what the app had already written there.** Declaring `[[volumes]]` for data an app kept in `src/` used to delete that data: the deploy replaced `src/` before linking the new, empty volume. The old tree is now set aside until the volumes are linked, and an empty volume is filled from it first, then from what the build produced.

- **Volumes are linked after the build, before the app starts.** They used to be linked before the build, where a `before-build` that unpacks the application and moves its directories into place collided with them.

- **Each app runs with its own `HOME` and `TMPDIR`**, `<app>/home/` and `<app>/tmp/`, where they were the server's own `/home/hop3` and `/tmp`. Every app shared one `~/.ssh`, so Gitea and Forgejo could rewrite the `authorized_keys` that holds Hop3's git-push keys, and every app's caches landed among the server's files. It covers the workers, `before-run`, the `[admin]` and `[probe]` `create` commands, `hop3 run` and `hop3 app shell`. The `create` commands also stop inheriting the server's whole environment: they get the workers' environment, including its precedence (a toolchain-owned variable is not overridden by `[env]`). Build steps keep the server's `HOME` for now, where the toolchains and their caches live.

- **A generated Nix app writes its config files and runs its `pre-exec` once per deploy, before it starts.** They used to run in the wrapper on every start: inside the start timeout, which BookStack's migrations outlasted, and as files the running app wrote into `src/`. They now run as the build's own before-run step, ahead of `[run] before-run`, and a failure fails the deploy. A hand-written `hop3.nix` gets the same with a `before_run` list in its `runtime.json`. Likewise, `writable-home-at-runtime` now copies the package into `src/` at deploy time, as the writable tree, where the wrapper used to copy it into `src/.<name>-home` on first start; `$PWD`, not `$HOME_DIR`, is where it lives.

- **A Nix-built PHP app is served by php-fpm, as a native one is.** The `php-app` template served it through PHP's single-threaded built-in server, where an app that requests its own URL deadlocks against its only worker; `serve-mode = "fpm"` is now its default, and `builtin` and `artisan` remain for a recipe that asks. A hand-written `hop3.nix` asks for the pool with a `php_fpm` entry in its `runtime.json`: Hop3 writes the pool, runs it, and has the proxy speak FastCGI to it, refusing hidden files and the recipe's `[proxy] deny` paths.

- **A `git push` stops the running app before replacing its source**, as `hop3 deploy` already did. A process still holding files in `src/` could race the rebuild.

- **The server checks the account's role on every command and every dashboard page.** Until now any account could run everything but user management. A command above the account's role is refused with the role it needs and the `hop3 user set-role` that would grant it, and `hop3` exits with code 5. The dashboard refuses a page the same way and sends a member to its profile.

- **A new account is a `member` until an admin grants it more.** Upgrading keeps admins as admins and makes every other account a deployer, which is what it could already do. A member gets no API token.

- **Generated Nix recipes build against nixos-26.05**, from nixos-24.11, with pnpm 10 as the default pnpm. Dependency hashes recorded against the old pin may need recording again, from the `got:` line of a failed build; a recipe that pins its own `nixpkgs-rev` keeps its pin.

- **`go-frontend-source-root` names a directory in the repository** (`frontend`), found under whatever directory the source unpacks to. It used to include the release archive's top-level directory, which changes with the fetcher; that form is now refused with the fix in the message.

- **`hop3-install server` stops when it cannot install Node 22.** When NodeSource was unreachable it installed the distribution's Node 18, which is past end of life and too old for the Node apps in the catalog; the install succeeded and those apps failed later, at build. It now stops at that step with the reason, and likewise when an older Node is still first on `PATH` after the install.

- **On a Docker install, supervisor calls the uWSGI emperor `uwsgi-hop3`**, the name of its systemd unit elsewhere, instead of `uwsgi`. Use `supervisorctl restart uwsgi-hop3`. The next `hop3-deploy-server` rewrites the configuration.

- **A command missing an argument fails, with its usage.** It used to print the usage and exit 0, so `hop3 addon postgres export > dump.sql` without a name wrote "Usage: ..." into the dump and reported success. It now prints the usage from the command's help on stderr and exits 2.

- **`hop3 addon show`, `status`, `destroy`, `attach` and `detach` read an addon's type from its name**, like `addon expose` and `addon promote`. Without `--type` they assumed postgres, so a Redis addon was looked up as a database that did not exist. A name two types share is refused until `--type` says which.

- **`hop3 cert renew` takes `--app <app>` and `--force-renewal`**, in place of a positional app name and `--force`, which the CLI keeps for itself: `--force` skipped a confirmation and the server never saw it, so a forced renewal renewed only the certificates already due.

- **`hop3 nix eject --app <app> > hop3.nix` prints the generated expression.** It wrote the file into the server's copy of the source, which the next deploy replaces. Save it in your project and remove the `[nix]` section from `hop3.toml`: a build refuses an app that has both, which the command used to say it would ignore.

- **A token for a deleted or disabled account stops working on its next call.** `hop3` and `hop3-tui` now show the server's reason, where they used to print a bare "authentication required" or HTTP status.

### Security

- **An app can no longer call hop3-rootd.** Every native app runs as `hop3`, the uid rootd admits, so any app's code could ask the privileged helper for anything: root, with no exploit. rootd now also refuses a caller running inside the app runtime: the `uwsgi-hop3` service's cgroup or `hop3.slice` under systemd, and descendants of the uWSGI Emperor on a host without systemd (weaker: a process that double-forks escapes it). Apps still share one user, so one app can read another's data until per-app users land (planned for 0.9).
- **A gated app's nginx include file cannot forward around the gate.** The gate replaces the client's `X-Hop3-User`, `X-Hop3-Role` and `Cookie` in the locations Hop3 writes; a location in `NGINX_INCLUDE_FILE` with its own `proxy_pass` inherited none of that and forwarded whatever identity the client sent. Such an include is now refused on an app with `[access]`.
- **Scaling a process type down removes that worker's copy of the app's secrets.** Each worker's environment is a `0600` file; a removed worker's file stayed on disk, and a later rotation never updated it.
- **Database passwords no longer appear on a command line.** The installer set the PostgreSQL superuser password with `psql -c "ALTER USER ... PASSWORD '...'"` and created the MySQL `hop3` user with `mysql -e`, both readable by any local user in `/proc/<pid>/cmdline` while they ran; the SQL now goes on stdin.
- **The test harness no longer creates admin accounts.** It created `hop3-harness` and `tutorial-runner` with their usernames as passwords, published in the repository, and on a `--host` server they outlived the run. It now takes a token from `admin:ssh-token`, as `hop3 login --ssh` does. Servers the harness ran against should have those two accounts removed.
- **The test harness no longer replaces a server's mail setup.** It switched any server to the `catch` backend for apps that declare email and never switched back; it now does so only when no backend, or `catch`, is configured, and refuses otherwise.
- **The tutorial runner no longer puts the admin token on a command line.** On a remote target it passed `HOP3_API_TOKEN=<token>` in the shell line it runs, readable by any local user while validoc ran; the token now stays in a `0600` file on the server, shared with the harness's other admin steps.
- **`hop3` and `hop3-tui` refuse a malformed API token without printing it.** A token holding a line break (two tokens read from one file) made the HTTP library reject the `Authorization` header with an error that quoted it, and the client printed that error, token included.

- **A PHP app's hidden files are no longer served.** nginx served `.env`, `.htaccess` and anything else under a PHP app's document root whose name starts with a dot, apart from `.git`. nginx and Caddy now answer them with 404, except `/.well-known/`. The fix takes effect when an app is next deployed.

- **An app's environment is no longer visible to other users on the server.** Background workers, php-fpm pools and every app started with a start command received their `[env]` as `export` statements on a command line that stayed visible to `ps` for as long as the app ran. Any local account could read every app's secrets that way, including the web server's and the database's. The environment now goes to a file readable only by the app's owner. The fix takes effect when an app is next deployed; `hop3 app restart` reuses the old configuration, so redeploy each native app, or stop and start it.

- **A server installs no dependency released in the last seven days.** A compromised package is usually caught and yanked within days, and an install resolving the latest version would take it the hour it appears. The installer writes the cutoff into the server venv's `pip.conf`, so upgrades and developer deploys resolve under it too. Hop3's own packages are exempt, so a release can be installed the day it ships. Apps' own builds are unaffected.

### Fixed

- **`hop3 app upgrade` works for an app built from a `[nix]` template.** The generated expression was written into the source tree as `hop3.nix`, so a second deploy from that tree (an upgrade, and the restore that rolls a failed upgrade back) refused it as "both hop3.nix and a [nix].template". It is now `.hop3-generated.nix`; a `hop3.nix` an earlier deploy generated, identical to the template's output, is replaced.
- **A redeploy without new source builds from the source the app was delivered with.** `hop3 app upgrade`, a backup restore and `hop3 app scale` ran the build again on the previous build's output, so a recipe that downloads and unpacks its application met its own leftovers: LimeSurvey's upgrade failed with `mv: cannot overwrite './vendor'`, and so did the rollback. Each deploy keeps the tree it delivered (`src.delivered`), every build starts from a copy of it, and backups carry it. An app deployed by an earlier version keeps building in place, with a notice, until its next deploy.
- **A PostgreSQL restore gives back the dump, or fails and changes nothing.** The dump was replayed over the live database: its CREATE statements failed on the tables already there, `psql` carried on and exited 0, and the restored database mixed the backup with what it was meant to replace. That is the database an upgrade's rollback left. The dump now loads into a fresh database, in one transaction that stops at the first error, and replaces the live one only once it loaded.
- **A slow or failing server is no longer reported as a missing credential.** Before a destructive command, the CLI checks its credential with the server, and any failure of that check, a timeout included, became "No credential for ...", exit 4, and the advice to log in again: a destroy sent while the server was still busy with an upgrade said so. Only a refused credential is now an authentication error; a timeout or a server error is reported as itself. A read timeout, which no handler recognised, now says the server did not answer in time. These messages are printed on stderr.
- **A recipe whose probe account cannot be created fails its test.** The deploy carries on past a failed `[probe].create`, and the app's check then signs in as the operator. Six published recipes passed a whole run that way, their probe commands broken. `hop3-test` now fails such a test and quotes the deploy's reason, and the check's summary no longer says "no [probe]" for a probe that was declared.
- **A failed tutorial names the step that failed.** Every tutorial failure was classified `build-failure` and pointed at an empty build section, an output mismatch included: validoc's `Error: Expected exit code` matched the build-error pattern. A failed tutorial is now a `step-failure` whose headline quotes validoc's failed step and its error, and points at the section holding the step's output.
- **A Nix node-gyp addon that never included `<cstdint>` builds again.** The libstdc++ in the nixos-26.05 pin no longer pulls `<cstdint>` in through `<memory>` or `<functional>`, so `isolated-vm` 5.0.3, which every Directus release still pins, failed with "'uint32_t' has not been declared". The `node-pnpm-install` template now compiles every declared `node-native-packages` addon with `-include cstdint`.
- **A Nix hash mismatch's headline gives the hash the build got.** Nix ends its first line at the derivation, so a failed `hop3-test` app's verdict quoted that line and stopped before the value to put in the recipe. It now names the derivation, the recipe's hash and the one the build got. The text report also no longer prints "No failures recorded." beneath a list of failed tests when the target itself had none.
- **A command that hangs on a test target fails, naming itself.** Neither the Docker exec nor the SSH channel bounds a command, so one that hung left a `hop3-test` run silent, with no error, for as long as it hung. Every command the harness runs on a target is now bounded there (300 s unless the caller sets more; a tutorial gets 900 s), and one that runs past it is killed and raises an error naming the command, the limit and its last output.
- **A test run no longer changes your CLI's default context.** Every Docker deploy the test harnesses make (`hop3-test`, the pytest e2e targets) signed the developer's own CLI in to the throwaway container and made it the default context, so once the run removed the container, every plain `hop3` command went to a dead address. The harnesses now deploy with `--no-cli-setup`; a `hop3-deploy-server --docker` run by hand still configures the `hop3-docker` context.
- **A MySQL backup no longer logs an access error.** `mysqldump` dumps tablespaces by default, which needs the server-wide PROCESS privilege the app's user does not have; it said so on every backup, and every upgrade's snapshot. Dumps now leave tablespaces out.
- **A build command waiting for input fails instead of hanging the deploy.** Build steps inherited the server's stdin, which under supervisor is a pipe nobody writes: `unzip` asking whether to replace a file held a Vikunja upgrade until the client gave up. Build, before-run, admin and probe commands now read from `/dev/null`.
- **An app with an email addon can be backed up, and so upgraded.** The email addon refused to be backed up because it holds no data, which failed every backup of such an app, and every upgrade, whose snapshot is a backup. The backup records the addon by name, without its settings; a restore checks it is still configured, and names the command that re-creates it otherwise.
- **The server's own log messages survive its database migrations.** Alembic's logging setup, run in-process at startup, disabled every logger created before it: among them, the catalog loader's report of the apps it excludes.
- **A catalog install checks the server features the index names, whatever the version number says.** A server built from the development branch carries the previous release's number, and refused every recipe declaring the next one in `requires_hop3`. That field is checked only for catalogs published before feature names. The publisher writes `requires` for every entry, empty included: an entry without it read as one published before feature names.

- **The executable tutorials pass on Docker again.** The test domain carried the Docker target's SSH user (`hop3@<ip>.sslip.io`), so every tutorial's hostname step was refused; on a target named by hostname it was `<name>.sslip.io`, which sslip.io does not resolve; and all 33 checked their app over `http://`, which the platform redirects. Tutorials now check `https://`; the harness accepts the test server's self-signed certificate. A tutorial also gets the server its `hop3.toml` asks for (Nix, its addons), as an app does.
- **Two deploy steps no longer carry on past a failure.** A served tree the web server could not be granted read on (every asset then answered 403), and a volume that could not be given to the app's user (the app then could not write it), were logged and the deploy reported success. Both now stop it, naming the path and the error.
- **A test run names every test it left out, and why, whatever the verbosity.** Tests dropped for a missing service, a missing admin domain, or a Docker build on the Docker target went through warnings that `--quiet` silenced and never reached the report; they are now listed when dropped and again after the summary. A failed app destroy at cleanup is shown the same way, and fails an upgrade chain, whose `--host` server keeps whatever the teardown left.
- **An app's `[admin]`/`[probe]` create command gets its `HOME` and `TMPDIR`.** They were created only when the app's workers started, which happened to come first.
- **The `hop3.toml` JSON schema lists the `[access] role` values**, so an editor completes and checks them.
- **A Nix app's `runtime.json` cannot declare a `web` worker beside a php-fpm pool.** The pool replaced it without a word; both together are refused, naming the keys.
- **nix-gen checks `serve-mode`, and `strip-components`/`executable` beside `github`, when `hop3.toml` is read.** A typo surfaced deep inside a deploy; the file-only keys were dropped silently.
- **The dashboard's role check no longer blocks the server.** It made two database reads per request on the event loop that every other request waits on; they run on a worker thread.
- **A 401 says which case it is in its data** (`error.data.kind`: `unauthenticated`, `account_unusable`), and the CLI and TUI read that instead of the message's wording.
- **hop3-rootd reports a service systemd has no unit for as unmanaged, not stopped.** `systemctl is-active` prints `inactive` for a missing unit, so an uninstalled proxy read as installed and down.
- **The .NET SDK step says why an SDK is missing.** A failed `apt-get update` stops the install; failing to add Microsoft's repository stops it on Debian, which has no .NET packages of its own, and on Ubuntu is named as the cause of any SDK then missing (the line said "not published"). On Fedora an installed SDK counts as available, which `dnf list --available` may not show.
- **A PHP document root must lie inside the application.** `[build].document-root = ".."`, or a Nix app's `web-root`, served the directory above it (or crashed the Nix build); both are refused with the key that set them.
- **A nix-gen template that installs one file refuses a GitHub source.** `java-war`, `prebuilt-binary` and `node-prebuilt` failed deep inside the Nix build on a `github = ...` tree; they now say to name the release asset.
- **A generated `hop3.nix` no longer names the wrong app.** Its eject hint used `[metadata].id`, which is not the name an app is deployed under; it now says to run `hop3 nix eject` in the app's directory.
- **A PostgreSQL password that cannot be verified says why.** The error now carries the `ALTER USER` and TCP-check output, which tell a refused connection from a wrong password from an `ALTER` that never ran.
- **A resumed download cannot splice two versions of a file.** A retry asked for the rest of the body with `Range` alone; a file replaced upstream between attempts got the new tail on the old head. A resume now names the version it continues (`If-Range`), and an unpinned download from a server that gives no version starts again from zero.
- **Production code no longer checks whether it runs under pytest.** Seven places skipped a hop3-rootd call, the Mailpit check or the port-25 probe when `PYTEST_CURRENT_TEST` was set; the test suite now replaces those dependencies with fakes it declares.
- **Mailpit is reported running when it answers.** The installer printed "Mailpit running" on the restart's exit code; it now waits for the SMTP greeting and stops if none comes. A Mailpit archive without the binary is refused instead of crashing the installer.
- **The upgrade-chain check cannot pass vacuously.** The seeded account's rights on the first hop were recorded as found, so a probe that failed there compared equal on every later hop; the seed now must have a plain account's rights.
- **The installer says why a service would not start.** Redis and MySQL failures aborted with "did not restart" and nothing else; the failing command's output and the unit's journal now come with it. Redis is given time to listen after a restart, which an init script does not wait for.
- **A Nix app on a server without Nix is refused whichever way its builder is chosen.** Auto-selection declined it and moved on, so an app with a Procfile beside its `hop3.nix` was built by another builder without a word.
- **`server email status` names the backend in every case** (`none`, `relay`, `catch`, `direct`).
- **Ruby apps whose lockfile was written by Bundler 4 build again.** Hop3 installed gems with `bundle install --frozen`; Bundler switches itself to the version that wrote the lockfile, and Bundler 4 removed `--frozen`, so every such app failed to build. Frozen mode is now set through `BUNDLE_FROZEN`, which both read, and an app without a `Gemfile.lock` is refused with the command that makes one.
- **nginx accepts any legal hostname.** Its default `server_names_hash_bucket_size` (64) rejected a long name (`hop3-tuto-nix-gen-flask.135.181.203.156.sslip.io`) depending on which other vhosts were present, and the deploy failed `nginx -t`. The installer sets 256 in `/etc/nginx/conf.d/hop3-http.conf`.
- **Updating a server reconciles the platform's own settings.** `hop3-deploy-server` on an existing server updated the code and ran the installer only when features were requested, so a setting the platform added never reached a server installed before it; the nginx setting above first missed the very server it was written for. A plain update now runs the installer's `--reconcile` mode, which applies those settings and restarts nothing that runs apps. The full installer no longer restarts uwsgi-hop3 unless its unit changed: every redeploy with `--with` bounced every app.
- **The server's npm is pinned (11.17.0), like its pnpm.** Node 22 ships npm 10, which crashed installing a project scaffolded by the current NestJS CLI (`Cannot read properties of null (reading 'edgesOut')`). The installer reconciles npm on every install and stops if another npm shadows it on PATH.
- **An `[env]` value that is only `$NAME` is refused**, like `${NAME}` already was: `[env]` is exported literally, so `NITRO_PORT = "$PORT"` handed Nuxt the text `$PORT` and it died on startup. The message gives the section that works (`[run].start` for the port, `[env.computed]` with `${NAME}` otherwise). A `$` inside a longer value stays legal.
- **Tutorials teach what the platform accepts.** Django records exact versions (`pip freeze`); Sinatra keeps its `Gemfile.lock` instead of deleting it; Nuxt drops `NITRO_PORT = "$PORT"`, which `[env]` passes literally; the NestJS, Nuxt and Astro scaffolds are pinned to a major version.
- **A Nix app on a server without Nix says so.** `[build].builder = "nix"` on a server installed without `--with nix` stopped with `bash: nix-build: command not found`; it now names the missing Nix and the install command.
- **A nix-gen app built from its own directory now builds.** The local-source mode of three templates had only ever been parsed. python-venv emitted a wrapper Nix could not parse, node-pnpm-install wrote into a read-only copy of the app, and the pnpm dependency store hashed differently on every fetch because pnpm 10 records the build directory's path in it. Each template now has a fixture under `apps/test-apps-nix-gen/` that builds and serves. The pnpm fix changes every recorded `node-deps-hash`: directus-nixgen's must be re-recorded.
- **`070-php-public` asserted the pre-2026-09-25 answer for `/.env`** (the front controller); nginx now answers hidden files with 404, and the fixture says so.
- **The server installer stops at a failed setup step, with the command's output.** The systemd, SSL, nginx, PostgreSQL, MySQL, config-file and ACME steps caught their own failures, printed a warning cut to 100 characters, and the install went on to report success: a failed config write gave a server without database credentials. Verification now fails on a stopped core service, a missing certificate or a missing `hop3-server.toml`, where it warned. On a host without systemd, the installer writes the environment and key files, installs no unit, and says so, where `systemctl` failed and was reported as a "Systemd setup issue" on every container install. See `notes/installer-fail-loud-audit.md`.

- **`hop3-deploy-server` fails where it used to fall back.** With `--acme-email`, a failed Let's Encrypt issuance, a placeholder address or a missing acme.sh fails the deploy, where it installed a self-signed certificate and reported success; without `--acme-email`, self-signed is the default, said once. A failed admin user creation fails the deploy, where it went on to print login instructions for a user that did not exist. The CLI installer fails when the installed `hop3` does not run or provides no command, and shows a failed package install's output without `--verbose`.

- **The server installer's toolchain and service steps stop at the failure.** A failed install of npm's pinned pnpm, nodeenv or Go, a pnpm shadowed on PATH, Postfix for `--with email`, acme.sh, the S3 service or its token's group, the `www-data` and `docker` group memberships, an unsupported distribution, or the removal of the legacy sudoers fragment printed a warning and the install went on. The SSH key step could not fail at all: it printed "SSH keys configured" whatever happened. Rust, Leiningen and Elixir stay best-effort on every server and abort when requested: `--with clojure` and `--with elixir` join `--with rust`.

- **The database steps of the server installer stop at the failure, with its output.** A failed PostgreSQL `createuser` or `createdb` was printed as a detail and followed by "role and database created"; a PostgreSQL cluster that failed to start fell back to an older one; MySQL statements that failed returned quietly and a later check reported a generic error; the Docker-network MySQL user and the bind-address restart could fail with the install carrying on. Each now raises where it fails. A failed MySQL statement names what it did, never its text, which carries the password. Redis is made a primary in its config file, where the runtime commands that did it were discarded by the restart after them, is enabled under its Debian or Fedora name, and its check authenticates: with a password set, the unauthenticated `PING` it made was refused.

- **`hop3-deploy-server` installs Docker only when asked** (`--with docker`), on any target, as ADR 052 decided: Docker is a second-tier runtime. On the Docker target, where dockerd cannot run, `--with all` means every feature but Docker, and an explicit `--with docker` is refused with the reason, where it printed "Failed to start Docker daemon" and carried on.

- **The server installer installs the .NET SDKs 8 and 10**, the long-term releases, each where the distribution publishes it. It installed 8 and 9, and no feed carries 9 for Ubuntu 24.04, so that install failed on every such server and was printed as a warning. An SDK that is published and fails to install now aborts the install, as does a platform that publishes neither.

- **`hop3-deploy-server --docker` waits for hop3-server to answer before it reports the services started**, and a local CLI it could not configure fails the deploy. The login ran while the server was still starting, failed with "Could not connect", and the deploy still ended with "Deployment complete!". `--no-cli-setup` skips the step.

- **`hop3 login --token` checks the token it was given.** The check sent whatever the CLI already had stored for that server, or `HOP3_API_TOKEN`, so a new token for a server whose old one was no longer valid was refused with "Authentication required" without ever being sent. Every `hop3-deploy-server --docker --clean` hit this, since the new container signs with a new key.

- **`hop3-fetch` resumes a download cut short.** A retry used to start again from the first byte, so a server that drops long transfers failed every attempt: releases.wikimedia.org drops a transfer after about 75 seconds, and cut mediawiki's 116 MB tarball six times running, each time between 47 and 80 MB. A retry now asks for the rest with a `Range` request and checks the reassembled length against the total the server declares. Only an attempt that brings no new bytes counts against the six allowed, so a slow link that advances a few MB per attempt finishes. A connection reset mid-body is retried like a timeout, where it used to end the build with a traceback.

- **A redeploy after a failed deploy works the first time.** After a deploy failed while setting up the proxy, the next deploy of the same app failed once with `Cannot transition app from STOPPED to RUNNING`, then succeeded. A failed deploy now leaves the app `FAILED` with the error that stopped it, where it used to leave it `STARTING`, and the request no longer races the build over the app's state.

- **Caddy serves apps.** Every deploy on a Caddy server failed validation: Hop3 named each app's config `<app>.caddy`, which Caddy reads as JSON. With that fixed, an app that allowed plain HTTP still answered only on port 443, and the client address reached the app as `ip:port`. Caddy now also serves PHP apps through their php-fpm pool.

- **Traefik serves apps.** Its routes named a certificate resolver nothing defined, sent plain HTTP nowhere, routed only an app's first hostname, and told the app every request was HTTPS. They now use the certificate Hop3 issues, route every hostname on both ports, and refuse `/.git` as the other proxies do.

- **A deploy the server's proxy cannot serve is refused before the build.** Traefik proxied HTTP to php-fpm and sent static files to an address it cannot open, and Caddy and Traefik routed a `[waf]` app around its firewall; each deploy reported success. They now stop with the reason: Traefik serves no files and speaks no FastCGI, and only nginx fronts the WAF. The certbot engine is likewise refused on Caddy and Traefik, since Hop3 obtains and renews its certificates through nginx; use the self-signed engine there.

- **A Nix recipe built with `node-pnpm-install` says why its install failed, and installs under pnpm 10.** The install ran with `--reporter=silent`, so a failure read "builder failed with exit code 243" and nothing else. It also installed from the read-only fetched store, which pnpm 10 writes into; it now copies the store first, as nixpkgs does. And the rebuild of the native packages a recipe declares (`node-native-packages`) now runs under pnpm 10, which skipped them without a word, so the build succeeded and the app failed at start.

- **`hop3 system status` works on a server whose services run under supervisor.** It shelled out to `systemctl`, which a Docker install does not have, and failed outright. It now asks the process manager through hop3-rootd, and checks the proxy the server runs rather than always nginx, so a Caddy or Traefik server no longer reports nginx as down. `hop3 system status --json` also returns the structured report it was documented to: the client took `--json` as its own output switch and the command never saw it, so the "JSON" was the text report in a list.

- **`NGINX_INCLUDE_FILE` and `CADDY_INCLUDE_FILE` name a file in the app's repository.** They were resolved one directory above it, so a file the app shipped was reported missing unless the path started with `src/`, and a missing file stopped the deploy with a traceback. A path outside the repository is now refused, and so is a missing file, each with the variable's name.

- **`hop3` passes each command the flags its help documents.** The CLI refused `--app` for `addon list`, `addon promote`, `backup list`, `app create` and `cert renew`, so `addon promote` could not be run at all, and it split `ps scale` so the server ran `ps` instead. It also consumed `--dry-run` for every command but `deploy`, with a warning, so `system cleanup --dry-run`, `admin reencrypt-credentials --dry-run` and `app migrate --dry-run` ran for real; it now hands the flag on, and a command without a preview refuses it. `system info -v` lists plugins again and `system status --quiet` prints its one line. A test now checks every flag a command reads, every example in its help and every command line in the guides and tutorials against what the CLI sends.

- **`hop3 addon status` works.** It failed on every call, reading a type option it did not declare.

- **`hop3 nix eject` ejects.** Every invocation printed the command's help and did nothing.

- **The tutorials attach addons the way the CLI takes them**, `hop3 addon attach <addon> --app <app>`: fifteen lines had the app first, as a positional, and nine told `hop3 app logs` to `--tail`, an option it does not have. `hop3 backup list` takes the app as `--app` in every guide.

- **`hop3-install server` fails when pip fails.** A failed `pip install` of hop3-server, hop3-rootd or hop3-cli was ignored, and the installer printed "installed successfully" over it. It now stops at that step and shows pip's output.

## [0.7.5] - 2026-09-21

### Added

- **PHP apps are served by php-fpm behind nginx, and need no start command.** Delete `[run].start` from a PHP recipe: nginx serves static files from disk and passes `.php` requests to a per-app pool, with the front-controller fallback every framework expects. `php -S` and `artisan serve` are development servers and single-threaded, so an app that makes an HTTP request to itself (Nextcloud, Matomo) hangs until the request times out. Declaring `[run].start` still overrides the pool, which is how you would run Laravel Octane or FrankenPHP.

- **`[build].document-root` sets a PHP app's web root** when it is not one of `public/`, `web/`, `htdocs/` or `www/`, which are detected. Getting it wrong publishes your `.env` and your `vendor/` tree, so a value that is not a directory fails the build, and only the document root is made readable by the web server. Replaces `PHP_DOCUMENT_ROOT`, which never took effect.

### Fixed

- **`hop3 help` and `hop3 <command> --help` reach the server again.** With a context configured, `hop3 --context prod app --help` printed the built-in command list and "Not connected to a server yet" while the same context served `hop3 --context prod system info`. `hop3 login`, `hop3 settings show` and `hop3 completion refresh` gave the same wrong answer. The CLI was looking for a context's address under a key it stopped using in 0.7.4.

- **A worker command must be a single program.** `start = "setup.sh && serve"` ran `setup.sh` alone, silently. Hop3 now rejects a chained command and points at `[run].before-run`, or `bash -c '…'` if you want a shell.

- **A `node-pnpm-install` Nix app builds from scratch again.** The step that fetches dependencies also compiled native addons, so it depended on a C++ toolchain and on file permissions rather than being a plain download. Nix reuses a store path it already has, so this stayed hidden until a machine was rebuilt. Recipes using this template must re-record `node-deps-hash` from one build; Nix prints the value to use.

- **A Nix app built from its own directory no longer copies `.git` or the generated `hop3.nix` into the store.** A clone left by `hop3 launch <repo-url>` could carry a remote URL with a token in it.

- **`hop3-test` checks a PHP app through the proxy.** It probed the app's own port with an HTTP client, which a php-fpm pool does not speak, and reported a working app as crashed.

## [0.7.4] - 2026-09-15

### Security

- **A test run can no longer rebuild a cloud server.** `hop3-deploy-server` validated `--docker --provider` only after acting on `--provider`, so an installer unit test issued a real rebuild on any machine with `HETZNER_*` exported. Targets are validated before anything is provisioned, pytest strips the cloud credentials. A rebuild now requires the server label `hop3-throwaway=true`.

### Added

- **`[proxy]` sets the reverse proxy's limits per app.** `max-body-size` (`2G`, or `0` for no limit) and `request-buffering = false`, rendered for whichever of nginx, Caddy or Traefik is active. Uploads were capped at a hardcoded 50 MB with no way to raise it.

- **Garage replaces MinIO behind the S3 addon.** MinIO withdrew its server binaries, which broke `hop3-install server --with s3`, and with it the whole install. Apps see the same endpoint and per-bucket key. Existing MinIO data is not migrated; `HOP3_S3_BACKEND=minio` still selects the old backend. (ADR 060)

- **`hop3-backup-server` snapshots a whole server.** The control-plane database, config and secrets, the apps tree, and dumps of PostgreSQL, MySQL, Redis and, on request, Docker volumes. `--fetch DIR` brings the snapshot home; every step reports ok, skip or FAIL.

- **`hop3-restore-server` puts a server back to a snapshot.** `--only` restores a subset, `--from-local` uploads one fetched earlier. It keeps a `.pre-restore` copy of everything it replaces and reports success only once the server answers.

- **The CLI talks HTTPS by default; SSH is bootstrap and rescue.** Signing in over SSH recorded the SSH target as *the* connection, so every later `hop3 apps` or `hop3 logs` opened a root shell. A login now records the server's public address and uses SSH only to mint a token; a server without a trusted certificate keeps the tunnel and the login says so. `--via-ssh` forces one command through SSH.

- **Every target the CLI can reach has a name.** `hop3 login` wrote an unnamed default target that sat below every context, so a login could report success and then send every command elsewhere. A login with no `--context` now writes the reserved context `default`. `HOP3_API_URL` appears as the context `env`. Existing configuration is migrated on first run.

- **`hop3 login` takes its target positionally**: `hop3 login root@server`, with `--browser` for a dashboard magic link. The old `--ssh` and `--web` spellings still work.

### Fixed

- **A deploy no longer claims the CLI's `default` context, or points it at the API port.** It signed this machine in by passing `--context default` explicitly, which skips the guard that refuses to move an existing `default` onto another server. It also pointed the CLI at `http://<host>:8000`, the API in clear. An SSH deploy now configures nothing and gives one login command, which negotiates HTTPS or a tunnel itself; a `--docker` deploy still configures the CLI, under the context `hop3-docker`.

- **The deploy banner stopped contradicting itself.** It told you to run `hop3 login root@<host>` after writing the context that makes the CLI refuse exactly that; then, once fixed, gave three different spellings of one command and never said what `--context` does. One command now, with its variations as added flags. `Server URL:` now names `https://<admin-domain>`.

- **A login is visible to the rest of its own invocation.** The context reached disk, but this process had resolved its connection before that. The cache refresh that runs on the back of a login therefore reported "API URL not configured" one line under "Signed in to …", about the server it had just signed in to.

- **Refusing to repoint `default` says whose the two addresses are.** Almost always one machine by two routes, since the deployer wrote the first; the refusal listed both and left the reader to guess they had two servers.

- **"No server configured" names a real command and an obvious placeholder.** It said `hop3 init --ssh root@server`, which reads as a real target: typed as printed it fails with `Could not resolve hostname server`.

- **A deploy that times out while the app is answering now says so.** When `[healthcheck].contains` never matches, the failure names the path, the status and what the page actually contained. It used to report a dead worker and advise a longer timeout.

- **`hop3-test` runs an app's `check.py` with the credentials the deploy uses.** It exported only `HOP3_ADMIN_*`, so every check signed in as the operator, never the app's `[probe]` account, and reported working apps as broken.

- **The pnpm version a server builds with is pinned.** It was whatever `npm install -g pnpm` fetched on install day and was never reconciled, so servers drifted apart; pnpm 12 removed a flag Etherpad calls at every boot. The app died four seconds into startup. Upgrading a server installs the pinned version.

- **Health checks identify themselves** with a `hop3-healthcheck` User-Agent. Apps that reject anonymous requests (GoToSocial answers 418) failed readiness while serving everyone else.

- **A readiness timeout names the port the app actually bound.** An app that ignores `$PORT` (Grafana defaults to 3000) was reported as slow to start. The failure now lists the ports the app's own processes hold and points at `[run].start`.

- **`${VAR}` in `[env]` is refused at validation.** `[env]` does not interpolate, so a recipe using `${PGHOST}` there got the characters: Grafana ran on SQLite beside the empty PostgreSQL addon Hop3 had provisioned. The error names the section that does: `[env.computed]`, or `[run].start` for `$PORT`. `[env.computed]` now fails the deploy on a missing reference, where it used to store the template.

- **Deploys are no longer refused at random for an nginx reload that worked.** A rounding error in the reload's freshness check rejected workers that had just forked, aborting the deploy with "nginx kept the previous config".

- **A failed nginx reload reports what it measured**: the reference tick, the workers it saw, whether the error log was readable. It used to say only "no fresh worker processes appeared".

- **`hop3 run` streams its output and no longer times out.** Long commands were killed at five minutes and showed nothing until they ended. Output appears as the program prints it, stderr interleaved.

- **A streamed `hop3 run` no longer signs off with "App deployed successfully".**

- **A long-running stream is no longer dropped after an hour.** Only finished streams are collected. The replay buffer is bounded.

- **Readiness probes php-fpm over FastCGI.** The gate opened a plain HTTP connection, which no php-fpm pool can answer. A backend declares its protocol in the build artifact and the proxy reads the same field.

- **A proxy config the server rejects is rolled back.** One bad vhost aborted every later deploy and every certificate renewal, naming an app neither of them touched. The rejected file is parked as `<app>.conf.rejected`, outside the include glob, and named in the diagnosis.

- **Caddy and Traefik abort when they cannot validate a config**, as nginx already did.

- **`hop3 run mycli --help` reaches the program.** Global flag parsing stopped at the program token; help handling did not.

- **A failed SSH bootstrap says what broke.** Connecting as a non-root admin failed with `su: Authentication failure`, naming neither the command nor the requirement. The error now carries both. `hop3@host` is refused up front.

- **The warning before a destructive command names the server address**, not only the context name.

- **The deployer writes a real context.** It used to write a deprecated setting that every context outranked, so "CLI configured to connect to `<host>`" is now true.

- **The docs linter stops calling `hop3 apps`, `login`, `logout` and `ssh` deprecated.** They are the intended short forms (ADR 036).

- **The deploy banner names a command that exists.** It offered `hop3 admin set-password`; it now gives `hop3 login root@<host>`, which needs no password.

- **An unknown command is reported in full.** `hop3 admin set-password` answered "Command 'admin' not found"; it now names the token that broke the lookup and suggests `user set-password`.

- **New page, Signing In (Get Started).** How the CLI and dashboard credentials differ, the one command that signs the CLI in, and a symptom-to-fix table. The material was spread over three documents that disagreed with each other.

- **`hop3 login --help` documents `--web`**, `--context`, and the password reset that does not need the password. The docs also stop offering `--ssh` and `--web` as alternatives: only the first is a login, the second prints a dashboard link.

- **The dashboard login page tells a first-time operator how to get in**: `hop3 login --web root@<server>`, since the generated password is never shown in the clear.

- **The CLI reference gives the real token lifetime**: 24 hours, not 30 days. The 14-day figure belongs to the web session, which is a separate credential.

- **Help and error text call the CLI `hop3`** throughout. `hop` still works.

- **Uploads work on a server with a non-standard SSH port.** `scp` was passed ssh's `-p`, which it reads as "preserve times".

- **An in-place server upgrade upgrades rootd and the CLI too.** They were left at the old version beside a new server, so the first addon change afterwards failed with "no such op". All three are installed at one version from one source. The venv is checked before migrations run.

- **`--from local` on the Docker backend no longer reinstalls the old code** and reports success: `docker cp` was nesting the new tree inside the old one.

- **The Docker update path works on a container created by an older deployer.**

- **`hop3-test upgrade-chain` actually upgrades.** It asked every worktree for the current deployer name. `uv run` answered a missing script by falling through to `PATH`, so each hop installed the current version. Every hop now asserts the version it claims.

- **The administration guide gives the real upgrade path.** Re-running the single-file installer does not migrate the schema and restarts every app.

## [0.7.3] - 2026-09-08

### Added

- **`hop3 app shell` opens a shell inside a deployed app**, with the environment its workers get: the toolchain's `PATH`, the addon credentials, `$PORT`, and the source directory as cwd. It travels over the SSH forced command that already serves `git push`, so nothing new listens. `hop3 ssh` is an alias. `hop3 run` now shares the same environment.

- **`hop3 env set` keeps secrets off the command line.** `KEY=-` reads the value from stdin, `KEY=@path` from a file. A bare `KEY` prompts with echo off, so it never reaches the shell history or `ps`. Output is redacted, including the previous value reported on an overwrite. (ADR 036)

- **`hop3 help` works before you log in**, from a command list the client refreshes at every login. A mistyped command gets a suggestion the server computes. `hop3 help --all --json` emits the whole command tree.

- **One SSH configuration for everything the CLI spawns.** `ssh_key`, `ssh_port` and the new `ssh_options` (`HOP3_SSH_KEY`, `HOP3_SSH_PORT`, `HOP3_SSH_OPTIONS`) are read by the RPC tunnel, `hop3 tunnel`, `app shell` and the login bootstrap alike. A port in the target (`root@host:2222`) is honoured everywhere; `ssh_options` takes a ProxyJump or a private known_hosts.

- **`[admin].verify` and `[probe].verify` prove a bootstrap account exists.** A zero exit is not evidence: Gitea and Forgejo reject the reserved name `admin` by printing an error and exiting 0, which once had Hop3 hand over a password for an account that was never created.

- **`hop3-tui` is rewritten on turbodesk and reaches `ssh://` servers.** It takes the server and token from hop3-cli, contexts and tunnel included, so the two clients can no longer disagree about which server they talk to. It gained a command line (`--server`, `--token`, `--version`) and a per-screen help dialog.

- **The documentation build produces `llms.txt` and `llms-full.txt`** for language-model readers.

- **PHP applications get a production runtime.** Ten catalog apps ran on PHP's single-threaded built-in server, where Nextcloud and Matomo deadlock against their own only worker. The toolchain now builds a php-fpm pool under the uWSGI Emperor. nginx serves the front-controller directory (`public/`, `web/`, `htdocs/`), keeping `.env` and the vendor tree off the web.

### Changed

- **PostgreSQL, Caddy and Traefik are reloaded through rootd.** Three call sites ran `sudo -n systemctl reload`, which fails on any host where the `hop3` user has no passwordless sudo. The PostgreSQL one also discarded the result, so a `pg_hba.conf` that was never applied looked exactly like one that was.

- **JSON-RPC errors carry JSON-RPC codes.** A malformed request body used to get an HTML 500 no client could parse. The endpoint now answers -32600, -32601 and -32602 for a bad envelope, -32001 unauthenticated, -32002 rate-limited, and -32603 for a command that failed while doing its work.

- **RPC commands and dashboard actions run off the event loop.** The server runs a single worker, so a multi-minute deploy froze authentication, the dashboard and every streaming log for its duration.

### Security

- **Stopping or destroying an app can no longer remove another app's worker configuration.** The sweep for `wiki` used the pattern `wiki*.ini`, which also matched `wiki-js`'s files; it now stops at the app-name boundary.

- **A symlink inside an app's tree can no longer point a backup or a volume outside it.** `[backup].paths` and `[[volumes]]` were checked lexically, so `src/data -> /etc` counted as inside the tree.

- **Login failures are indistinguishable, including in time.** An unknown username answered faster than a wrong password, because it returned before any hashing, so the response revealed whether an account existed (CWE-204).

- **A builder's refusal stops the deploy.** It was swallowed as "this builder does not apply", so the next builder in line built the app the wrong way. Two plugins claiming one identity now fail at startup. A hook implementation with no specification is an error, where it used to be a permanent no-op.

- **The PostgreSQL addon refuses a name that would derive a reserved role.** An addon named `pg-…` derives `pg_…`, which PostgreSQL reserves, and was rejected only after the database had been created.

### Fixed

- **A deploy no longer fails because nginx took more than two seconds to reload.** On a busy host a reload nginx had accepted could fork its workers later than that. The check now fails at once on a logged `[emerg]` and otherwise waits up to fifteen seconds.

- **`--with nix` either installs Nix or stops the install.** A failure printed a warning and reported success, so every Nix app on that server failed to build later. The installer also installs `xz`, which Nix needs and a bare Ubuntu 24.04 does not ship.

- **A restart against a garbage-collected Nix closure is refused for static sites too.** The guard gated on artifact kind. A Nix-built static site is a `static` artifact, so the restart reported success over missing files.

- **`hop3 run … python -c "…"` no longer loses `-c` to `--context`.** Global flag parsing stops at the program for `run` and `app run`, and at a POSIX `--` for every command.

- **`hop3 app destroy <name>` no longer asks you to confirm a different app.** A stray positional was rejected only after the prompt, which had already named the app resolved from the current directory. The app is always `--app`.

- **`hop3 app logs --help` reaches the same server as `hop3 app logs`.** Commands that need no authentication skipped context resolution and fell through to the legacy default server, which may be a retired one.

- **A reset tunneled request says why.** The reason is on ssh's stderr, which the error now carries; on "connect failed" it adds that the tunnel is up but nothing answers on the remote port.

- **The shell-completion cache survives a crash mid-write.** An interrupted write left a NUL-padded file that read as an empty command list, silently disabling completion. It is written atomically now, and honours `HOP3_CONFIG_DIR`.

- **`hop3.toml` accepts `[cli]`.** The CLI reads `[cli].app` as an app-resolution source, but the schema forbade the section, so a project following the CLI README was rejected at deploy.

- **Dashboard actions report their failure.** A restart, stop or backup that failed printed to the server's stdout and redirected to a page saying only "failed". An app whose `Procfile` or `hop3.toml` could not be parsed was rendered as "no workers".

- **`hop3-server plugins` reports a broken plugin.** Dropping it from the listing turned a plugin bug into "that feature does not exist".

- **Two apps can no longer share a name.** `app.name` is unique now; the migration aborts and names the duplicates if a database already holds two, since each owned its own env vars and addon credentials while every lookup by name raised.

- **hop3-test and the Docker e2e suite test what they claim.** The main deploy suite pointed at fixture directories renamed long ago, collected zero tests and reported "1 skipped"; it now runs 22 fixture deploys. A missing fixture directory is an error. Eighteen e2e tests that skipped on a default run now run: Nix, PostgreSQL backup and restore, archive integrity, and the SSH transport.

## [0.7.2] - 2026-08-30

### Added

- **The catalog says how well it knows each app.** Every recipe carries a maturity status: `golden` (signed into through the app's own login with the credential Hop3 generated), `beta` (deploys and serves its own content), and `alpha` / `broken` / `retired`, which are kept but never offered. Only the first two ship. The catalog gains a `status` field per app.

- **The catalog lists one entry per application**, with its other build paths behind it. Twenty applications had filled fifty-five slots, so `bookstack`, `bookstack-nix` and `bookstack-nixgen` competed with one another in search and for the front page. Nothing was withdrawn: every variant keeps its id, stays installable by it, and is still listed by `hop3 catalog list`.

- **The application gallery is live at `apps.hop3.cloud`.** A page per application with its screenshots and readme, category and tag pages, and a search index that runs in the browser. It is generated by a new package, `hop3-marketplace`, which imports the server's own catalog loader and taxonomy, so the public site and the dashboard on your server cannot disagree about what an app is.

- **An entry that would look unfinished can no longer be published.** `hop3-tools catalog lint` checks what an operator sees before installing: title, description, version, a category from the known taxonomy, tags, a memory estimate, an icon, a screenshot. It also refuses two entries claiming one id, which used to make one of them vanish with nothing logged. It runs as part of building the catalog.

### Security

- **Addon passwords are no longer briefly world-readable.** The file was created with default permissions, written, then locked down, so every write and rotation left a readable window. It is created locked down now. A half-finished write no longer leaves the app without one. Affects PostgreSQL, MySQL, Redis and email addons.

- **Two Redis addons can no longer be handed the same database.** The number was picked and written down three round trips later, so two `hop3 addon redis create` calls close together could take the same one and silently share keys. It is claimed and recorded in a single step, given back if the create then fails. When all fifteen are in use the error says which addon holds each.

- **Deploys no longer all build at once.** Each deploy got its own thread immediately, so ten `hop3 deploy` calls became ten simultaneous builds competing for the server that is also running your apps. Two build at a time (`MAX_CONCURRENT_BUILDS`) and the rest queue, saying so; past 32 waiting (`MAX_WAITING_BUILDS`) a deploy is refused.

- **`hop3 app create <repo_url>` checks the URL and bounds the clone.** A URL is not inert to git: `ext::sh -c …` runs its argument and `file:///…` reads any path the server can. Only `https://`, `http://`, `ssh://`, `git://` and `git@host:user/repo.git` are accepted. The clone is shallow, single-branch, and stops at 10 minutes or 2 GiB.

### Fixed

- **Catalog entries showed almost nothing they declared.** `catalog.toml` was never read by the server, so all fifty-five entries loaded without their tags, memory estimate, services or icon, and with one category between them. The dashboard compounded it by reading three field names the model has never defined. Both front ends now describe an application identically, checked by a test.

- **An app whose front page redirects is no longer reported as failing to start.** The content check read the first response and stopped. A redirect has no body, so Kanboard and Invoice Ninja could never satisfy a check they demonstrably passed in a browser. It now follows the app's own redirects, up to five, and never off to another host.

- **A comment in a Nix recipe could stop the app from starting.** Config files are written at startup by a shell that expands `${VAR}`, and ran anything in backticks too, so a recipe explaining itself in ordinary prose had those fragments executed and the app died at boot having built perfectly. Backticks in config content are text now. Four bundled recipes were carrying this.

- **The terminal UI showed invented logs and invented metrics.** `hop3-tui` displayed eight made-up log lines (including an error for an app that was fine) and fixed CPU, memory and disk readings dressed as live ones. It now shows your app's real logs, and says when a value has not been reported.

- **`hop3-test` could not run an app's smoke test at all.** It handed the check a plain-HTTP port while the check has spoken HTTPS for some time, so every app failed identically at "the admin credential signs in", which points at the credential and the app. The harness was at fault. Three faults were stacked behind it. A check now behaves identically whether a deploy runs it or the harness does.

- **`--keep` no longer reports that it destroyed the app it kept**, sending you to a static bundle while the app was still up for inspection.

- **A failed host-key scan in `hop3-test` says which host it could not read, and why.** The error was discarded, so a scan that timed out looked like one that never ran.

- **A signing key too short to sign with is refused.** `HOP3_SECRET_KEY` under 32 bytes weakens every token the server issues (RFC 7518 §3.2). PyJWT warned and signed anyway into a log nobody reads. Hop3 now stops with the length it found, the command to generate a good key, and the three places it looks.

- **`APP_START_TIMEOUT` now does something.** The reconciler was constructed without it and kept its hardcoded 60 seconds, so raising the setting changed nothing and a slow-starting app could be marked failed while it was still coming up.

- **Forgejo's licence is `GPL-3.0-or-later`, not `MIT`.** It relicensed at v9.0 and we package v14. Mattermost stays `MIT`, which is right for the binary Mattermost, Inc. publishes. The recipe now says so.

- **A truncated download is no longer cached and reused as if complete.** A connection cut mid-transfer poisoned the cache. Every later build reused the partial archive and failed somewhere further on, where the cause was no longer visible. The size received is checked against the size declared; `hop3-fetch --refresh <url>` re-fetches a poisoned entry.

- **A pinned pnpm dependency hash could mean different things on different machines.** The fetcher normalised the store's key order and timestamps but not file permissions, so a hash recorded on one machine failed on another with an identical lockfile, which a catalog install of Vikunja hit. Recipes can now ask for the normalisation nixpkgs added later (`node-pnpm-fetcher-version`).

- **Python packages with Rust extensions build under Nix.** The build derivation is sandboxed and offline, so cargo died reaching for crates.io; crates are vendored during the fetch step, which is the one place with network access. Gradle and PHP applications each had a gap of their own in the same generator.

- **A deploy can no longer report success for an app whose background worker never ran.** A missing command dies on spawn and is respawned, but the process manager announces throttling only several cycles in. On an idle server the same broken app passed, with a dead queue behind a login page that rendered perfectly.

- **A slow deploy upload no longer looks like a server that is down.** The bound meant for the connection handshake was applied to the body, so an upload needing more than thirty seconds was killed mid-send and reported as "Could not connect to the Hop3 server". A 20 MB deploy on a 2 Mbit/s uplink could never succeed. The body has its own allowance now. A large upload shows a progress bar.

- **An expired token no longer surfaces as "Unexpected response format".** An unauthenticated call was answered with a redirect to a login page, which the client followed, so HTML arrived where a JSON-RPC response was expected. The client no longer follows redirects from the RPC endpoint, which also stops a token being replayed to wherever the redirect points.

- **Installing a server from a git checkout no longer fails on a missing `hop3-fetch`.** An older layout simply does not ship it; only a helper that exists and cannot be linked stops the install.

## [0.7.1] - 2026-08-02

### Security

Affects every release up to and including 0.7.0. Upgrade if your hop3-server is reachable from an untrusted network. There is nothing to reconfigure and no credential to rotate. Change weak account passwords: until now they could be guessed far faster than intended.

- **Password guessing over JSON-RPC was not rate limited.** The web login form has been capped at 5 attempts per IP per minute since 0.5, but `hop3 auth get-token` checks the same credentials and applied no limit, so an attacker could guess ~100x faster by choosing that path. Both now draw on one shared budget.
- **Login failures revealed which accounts exist.** A disabled account answered differently from a wrong password. An unknown username answered faster than a real one. All three failures now return one identical response in the same time.
- **Signing in over plain HTTP looped forever.** The session cookie is `Secure`, so a browser with no TLS discarded it and the login bounced back to the login page forever, with no error anywhere. It now refuses up front and says why. Local development over HTTP still works with `HOP3_DEBUG=true`.
- **Signing out was a link, so another site could sign you out.** `GET /auth/logout` is now a form POST. Minor by itself, but it was the only state-changing GET, and "every mutation is a POST" is what lets Hop3 ship without CSRF tokens.

Details, and the remaining open items, in `notes/security/`.

One behaviour looks like a bug and is not. A magic link is spent the moment it is presented, even if the sign-in then fails because the account was deleted or disabled. A link that has been used cannot be replayed, whatever happened next. The one case where the link is *not* spent is a redemption that could never have worked for a reason you can fix: over plain HTTP, above, Hop3 refuses before touching the token, so the link still works once you reach the server over HTTPS.

### Fixed

- **Bugsink's Nix recipe runs its background worker.** The hand-written recipe deployed the web process alone, so the app signed in and then failed on any path that queues work: its "snappea" queue lives in a second database that was never migrated. Configuration and both migrations now run before any worker starts. The queue worker is declared alongside the web one. The other two Bugsink variants were unaffected.

## [0.7.0] - 2026-07-31

### Changed

- **Consistent command-line names**: the developer deploy tool is now `hop3-deploy-server` (renamed from `hop3-deploy`), part of a pass to give every Hop3 tool one consistent set of flags and verbs.
- **Failed deploys show the real cause**: `hop3 deploy` now surfaces the actual error line once, with a working pointer to the full log (`hop3 app logs --app <app> --build`).

### Added

- **Content-aware health checks**: set `[healthcheck].contains = "..."` and a deploy is only reported healthy when your app actually serves its own page: a bare `200` can be a placeholder or an error page.
- **Server-level email transport** *(experimental)*: set your SMTP submission credentials once with `hop3 server email set … --from-domain example.com`, and per-app email addons created without their own `--smtp-*` inherit them, with no credentials repeated per app. An app can still override with its own provider. Rotating the server transport propagates to every inheriting app.
- **Unified email backend selection** *(experimental)*: `hop3 server email backend <relay|catch|direct>` names the backend every declaring app inherits: `relay` (a provider or corporate smarthost, also spelled `server email set`), `catch` (a dev sink that captures mail and never sends it), and `direct` (below).
- **Direct / self-hosted email backend** *(experimental)*: `hop3 server email backend direct --from-domain example.com` turns the box into its own MTA: Postfix delivers to recipients' MX and opendkim signs outbound mail, with no third party. Hop3 generates the DKIM keypair and prints the exact SPF/DKIM/DMARC records to publish (plus the PTR reminder), runs an SPF/DKIM/DMARC pre-flight, and probes outbound port 25, never claiming "ready" over unpublished DNS or a blocked egress. Needs `--with email` (Postfix + opendkim).
- **Loopback email relay** *(experimental)*: selecting the relay backend now configures a queuing Postfix null-client on `127.0.0.1:25` (via hop3-rootd). An app that attaches an inheriting email addon is injected `SMTP_HOST=127.0.0.1`. It sends over SMTP to the local relay, which forwards to the provider, so the provider credential never enters an app's environment and the backend is swappable without re-touching apps. Install Postfix with `hop3-install server --with email` (included in `--with all`).
- **Email provider profiles + DKIM auto-verify** *(experimental)*: `hop3 server email set --provider <name>` fills the SMTP host/port for a known provider (`--list-providers`: Resend, Postmark, Brevo, Mailgun/Mailgun-EU, Scaleway TEM, with the EU-hosted ones flagged). The deliverability pre-flight now also **verifies DKIM** once its selector is known (`--dkim-selector`, or automatically for Resend); it used to check SPF/DMARC alone.
- **Operator email alerts** *(experimental)*: `hop3 server email notifications on` opts in to being emailed (via the active email backend) when things break: TLS certificate-renewal failures (a cert that stops renewing reaches you before it expires) and **failed deploys** (best-effort, never masking the failure itself). `status` reports whether the channel is actually deliverable. `test` sends a test message.
- **Safe app upgrades with automatic rollback**: `hop3 app upgrade --app <app>` snapshots the app, redeploys it (rebuilding and running its migrations), verifies it comes back healthy, and automatically restores the pre-upgrade snapshot if the build, a migration, or the health check fails. `hop3 app rollback --app <app>` restores a backup on demand (the most recent by default, `--to <backup-id>` for a specific one).
- **Install apps from the catalog, from the dashboard or the CLI**: 0.6 could browse the signed catalog; 0.7 installs and deploys from it. Twenty apps ship in the official catalog: BookStack, Bugsink, Dolibarr, Easy!Appointments, Forgejo, Gitea, Invoice Ninja, Isso, Kanboard, Keycloak, LimeSurvey, Matomo, Mattermost, Miniflux, Nextcloud, Paheko, Radicale, Uptime Kuma, Vikunja and WordPress. Each gets an admin account created for you at install time.
- **Every app is verified by signing in, not by returning a page**: each catalog app ships a smoke test that logs in through the app's own authentication with the credential Hop3 generated, and confirms a wrong password is refused. It runs at the end of every deploy (dashboard included), and on demand with `hop3 app check --app <app>`. A `200` from an app that nobody can log into no longer counts as working.
- **`[probe]`, a Hop3-owned account for verification**: an app can declare a non-privileged account whose password Hop3 owns and rotates, so its smoke test keeps working after you change the admin password. Apps that shouldn't have one can leave it out.
- **`hop3 scaffold`**: writes a starter `hop3.toml` for the project in the current directory, with a `#:schema` line so your editor completes and validates the file as you type.
- **Published `hop3.toml` JSON Schema**: at `https://hop3.cloud/schema/hop3.toml.json`, generated from the server's own validation models, so an editor with a TOML language server flags a typo as you type.
- **Every bundled app is verified under Nix too.** The two Nix build strategies are now held to the same sign-in bar as the native one: 16 of 16 hand-written recipes and 18 of 19 template-generated ones sign in and refuse a wrong password on a recorded run. Easy!Appointments is the exception: it builds its login form in JavaScript, which neither check can drive.
- **`hop3-deploy-server --provider hetzner --image <image>`**: rebuilds the target server from scratch before deploying, matching `hop3-test`. One command for a genuinely pristine box.

### Fixed

- **A failed server upgrade can no longer report success**: after installing the new code and migrating, the deployer now confirms hop3-server actually came back up before reporting the upgrade complete. If it didn't, the deploy fails loudly with the exact command to revert to the previous release, and a reminder that a forward-migrated schema may also need a pre-upgrade database backup. It used to leave a dead server behind a "complete" message. The restart also picks the right mechanism for the target (systemd or supervisor), so it can't silently keep serving old code.
- **Admin-domain and TLS setup fail loud on a broken nginx reload**: configuring the server's admin domain or its certificate during a deploy now stops with a clear error when nginx can't be reloaded, so a "complete" deploy never hides a domain that nginx never actually picked up.
- **Nix apps survive garbage collection**: a running Nix app no longer loses its files to a `nix` garbage-collect: new installs pin auto-GC off. Rebuilds keep the previous version rooted. If anything is ever missing, the deploy fails fast with a clear message. Apps that need a newer package set can pin their own nixpkgs revision.
- **`hop3 app restart` checks the Nix closure too**: the check above ran on deploy and start but not on restart, because a restart relaunches the worker from its existing config without going through the start path. A restart against a reclaimed closure therefore came up and died into a health-check timeout with nothing pointing at the cause. It now aborts with the same message naming the missing store path.
- **A fresh install no longer serves a stale configuration**: the installer now restarts hop3-server once its configuration file is written, so a first-time install picks up its operator email, database credentials and admin domain immediately. Previously, on a brand-new server the service started *before* that file existed and cached the empty values, so every app using the built-in admin account failed to deploy with "this server has no operator email", even though the setting was correct on disk. Redeploys were unaffected, which is what made it a fresh-install-only bug.
- **Build failures inside your Dockerfile are reported right away, not retried as phantom registry errors**: a step that fails in your own build (for example a truncated download surfacing as "tar: Error is not recoverable") is now surfaced immediately. It used to be mistaken for a transient container-registry outage and retried three times. Genuine registry blips are still retried.
- **Apps are served over HTTPS by default**: plain HTTP now redirects. Apps that set `Secure` cookies (most of them) were unloggable over the HTTP vhost, because the browser correctly refused to send the session cookie back. The login looped with no error.
- **PHP's built-in server gets more than one worker**: it is single-threaded, so any app that makes a request to itself while installing (Nextcloud's installer does) deadlocked against its own only worker and never finished.
- **A failed install can be retried**: installing an app from the catalog recorded it before deploying, so if the deploy failed, every retry was refused with "already exists", leaving an app you could neither use nor reinstall. A second install now resumes one whose deploy never completed.
- **`[build].build` runs in every language**: the setting was read and then ignored by seven of the twelve toolchains, so a project's declared build command silently never ran.
- **`--clean` reclaims addon databases**: a clean reinstall wiped Hop3's records but left the databases behind, so the next install found a populated database and adopted it. It now stops the apps, drops what it tracks, and sweeps databases it has lost track of. MySQL also refuses to adopt a populated database it holds no credentials for.
- **`hop3 app credentials` no longer shows a password for an account that was never created**: when an app's own bootstrap failed, the generated credential was still presented as if it worked. The failure is now named. A bootstrap error includes the failing command's output, where it used to give an exit status alone.
- **`--app` works on `app check`, `app upgrade` and `app rollback`**: the three commands documented the flag and then rejected it.
- **Addon teardown reports what it could not remove**, which used to be left behind without a word.
- **More bundled apps deploy and verify correctly**, from packaging and content-check fixes across several apps.
- **Authentication hardening**: remediated the findings from the June 2026 auth audit.
- **DNS**: fixed some server-side DNS resolution issues.

### Security

These are defects in Hop3's own bundled application recipes, all found by the sign-in check described above and none visible to a deploy that returned HTTP 200. Anyone who deployed the affected Nix variants should redeploy.

- **Radicale served without authentication.** The Nix recipes set the calendar server's auth type from a variable that defaulted to `none` and was never set, so every calendar and address book was readable by anyone who asked. Authentication is now declared in the recipe where no environment can switch it off. The config is rewritten on every start so a deployment that once ran open does not stay open.
- **Isso's moderation dashboard was served disabled.** Its config carried no administrator section, so `/admin/` never asked for a password. It is now enabled against the generated credential, comment moderation is on. The app refuses to start without the credential.
- **Published default passwords in three apps, under both Nix strategies.** Miniflux, Keycloak and LimeSurvey shipped literal credentials (`changeme`, `password123`), so the deployed instance had an administrator whose password is in this repository while the operator held a generated one that did not work. All six recipes now refuse to start unless Hop3's generated credential is injected.
- **Gitea and Forgejo deployed with open registration** under both Nix strategies, because the setting that disables it lived in a shell script only the native recipe carried, so the first visitor to a fresh forge could register an account.
- **Signing keys rotated on every restart.** The Gitea and Forgejo Nix recipes minted `SECRET_KEY`, `INTERNAL_TOKEN` and `JWT_SECRET` inside a config file rewritten at each start, which invalidates every session and makes 2FA secrets and stored credentials undecryptable. They are now generated once and re-injected unchanged.

## [0.6.2] - 2026-06-26

### Changed

- **The deploy host doubles as the admin domain**: `hop3-deploy --host h.example.com` now serves the Web UI at `https://h.example.com/` when no `--admin-domain` is given. IPs, `localhost`, or Docker targets keep the previous behavior (UI on port 8000).
- **Follow-up hints remember your selectors**: when a command suggests a next step, the CLI renders it with the `--context` / `--app` you typed. Copy-paste now stays on the right target.
- **Usage strings show `--app` as optional**: the app-scoped flag is now `[--app <app>]`, reflecting that the app is normally resolved implicitly.
- **`hop3 app env` removed**: the hidden duplicate of `hop3 env show --sources` is gone.

### Fixed

- **Bare host no longer serves the wrong app**: the control-plane vhost claims `default_server`, so requests with no matching Host reach the Web UI, not a random app. Distro default sites are cleaned up on redeploy.
- **Admin-domain TLS fixed on rootd hosts**: `acme.sh` reloaded nginx as the `hop3` user (blocked by rootd). The deploy now reloads nginx itself and checks for the cert on disk, which acme.sh's exit code did not guarantee.
- **Self-signed cert upgraded to Let's Encrypt**: a previously-issued self-signed certificate is now replaced when `--acme-email` is added. When self-signed, the deploy tells you why.
- **Server knows its own admin domain**: `hop3-deploy` records `ADMIN_DOMAIN` so magic links and `addon expose` URLs use the right hostname.
- **Dashboard login survives redeploys**: web auth now uses a signed JWT cookie, matching the CLI credential. Stays valid across restarts.
- **`HOP3_UNSAFE` production override now works**: the auth guards re-read the env on every call.
- **Unknown CLI flags fail loud**: the RPC argument parser rejects unrecognized tokens with an error, where they used to be dropped without a word. This also fixed `hop3 backup list --app X` ignoring the filter.
- **`hop3 context use` recognizes global contexts**: it no longer answers "not found", and points to the right mechanism (`hop3 login --context` or `--context` per command).

## [0.6.1] - 2026-06-24

A consolidation release: simpler context model, pinned nixpkgs for reproducible builds, experimental email addon, and a round of fixes.

### Added

- **Experimental email / SMTP relay addon**: provision an outbound relay as an addon, with environment injection following ADR 051 conventions.
- **Config-injection conventions (ADR 051)**: documented how Hop3 wires addon settings into apps; vikunja and monica now honor injected SMTP.
- **`hop3 auth get-token`**: print the current bearer token. `login` and `auth login` unified; `login --web` fixed.

### Changed

- **One context model (BREAKING, ADR 042)**: credentialed servers and project contexts are consolidated. A *context* is a deploy environment declared in `hop3.toml` under `[contexts.<name>]`. Credentials become invisible plumbing in `~/.config/hop3-cli/credentials.toml`; `config.toml` is secret-free. Existing connections are migrated on first run.
- **Reproducible Nix builds**: nixpkgs is now pinned to a specific commit across all recipes. Builds resolve the same toolchain regardless of the host's `nix-channel`.

### Fixed

- **`--context` resolution fails loud**: the CLI shows the full resolution chain.
- **Nix GC root retained across rebuilds**: prevents a running worker's closure from being garbage-collected mid-deploy.
- **Elixir runtime env**: `MIX_HOME` no longer clobbered.
- **Discourse**: assets precompiled at build time so the container binds `$PORT` within the health-check window.
- **Kanboard**: schema migrations finish before the readiness probe runs.
- **Addon `create`**: edge case that could report success when the addon wasn't created.
- **Nix flake builds and NixOS CI**: repaired and re-enabled.
- **App packaging**: archived Focalboard dropped; shlink/piwigo validations corrected; bugsink start-timeout raised; native Monica marked expects-failure.
- **Test Lab reporting**: completed-with-failures runs are recorded as *failed*; variant and demo name show correctly; quieter scheduler logs; queue details expanded.

### Security

- **`hop3.toml` holds zero secrets**: a committed-credential tripwire rejects secret-shaped values in committed env. Per-environment secrets are set server-side with `hop3 env set`.

## [0.6.0] - 2026-06-22

Per-app resource limits and volumes, richer addon commands, a signed app catalog, and a published ADR collection.

### Added

- **Resource limits (ADR 046)**: declare memory and CPU caps under `[limits]`, enforced for native and containerized apps. Server can set defaults and ceilings.
- **Volumes (ADR 046)**: persistent bind mounts and tmpfs, provisioned through rootd behind a default-deny allow-list.
- **Addon management**: `hop3 addon <type>` gains `query`, `clone`, `export`, `import`, `restore`, `flush`, `exists`, `promote`, `endpoint`, `expose`, and `tunnel`.
- **App catalog (ADR 049)**: load a signed catalog of installable apps; browse from the dashboard.
- **Configurable backup contents**: `[backup].paths` / `[backup].exclude`.
- **Static sites without a Procfile**: serve from `[build].static-dir`.
- **Fixed-port registry (ADR 045)**: non-HTTP apps claim a stable host port from `hop3.toml`, optionally with source CIDRs.
- **Generated env secrets**: `SECRET_KEY = { generate = "urlsafe" }` under `[env]`.

### Changed

- **`--app` flag only (ADR 036)**: deprecated positional argument removed.
- **Python 3.12+ required (BREAKING)**.
- **Command renames** (aliases kept): `launch` → `create`, `backup info` → `backup show`, `addon ps` → `addon activity`, `domains` → `domain`, `env migrate` → `app migrate`.
- **Single source for server secret (ADR 048)**.
- **Idempotent redeploys**: re-running the installer preserves existing secrets and operator config.

### Fixed

- **Redeploy no longer kills the git push**: the reaper leaves `git receive-pack` alone.
- **Stable app port across redeploys**.
- **Smaller deploy uploads**: build-output directories excluded.
- **Redis health check** fixed when no password is set.
- **Let's Encrypt email** forwarded to the installer on redeploy.

### Security

- **Hardened catalog dashboard**: untrusted catalog content sanitized.
- **Unavailable banner** when the catalog source is down.

### Documentation

- Full ADR collection published on the docs site.
- Guides, CLI reference, and tutorials reviewed and corrected.
- Testing walkthrough series and "Migrating from X" guides published.

## [0.5.0] - 2026-06-08

### Highlights

- **CLI server/context model (ADR 042)**: credentialed servers separated from per-project deploy contexts.
- **Unified testing architecture (ADR 043)**: one speed-tier taxonomy, shared diagnostic bundle.
- **Nightly Test Lab (ADR 044)**: web dashboard for run history and regressions.
- **Privileged-operations daemon (ADR 041)**: narrow root-boundary daemon replaces broad sudoers.
- **Security hardening**: RPC boundary, authentication, credential storage.

### Added

- **CLI ergonomics overhaul (ADR 036)**: a redesigned command surface: space-separated command names (`hop3 env set`), an implicit current app, a sticky working context (`hop3 use`), command aliases, did-you-mean suggestions, categorized help with an example on every command, scriptable confirmations and non-interactive flags, and secret inputs from a file or stdin.
- **Nix integration**: hermetic, reproducible builds from a `hop3.nix` file, a starter set of Nix-based application packages, and installer support for Nix on every supported distribution.
- **Computed environment variables**: interpolate values in `hop3.toml` with `${VAR}`, resolved after addon variables are injected, so platform variables can be mapped to the names an app expects.
- **WSGI auto-discovery**: Python web entry points are detected automatically when no worker is configured.
- **Servers and project contexts (ADR 042)**: manage credentialed hosts with `hop3 server` and per-project deploy targets with `hop3 context`.
- **Deploy preview and project-mismatch guard (ADR 042)**: `hop3 deploy` shows the resolved plan and confirms before acting; destructive commands refuse to run when the resolved app contradicts the current project.
- **Shared failure diagnosis (ADR 043)**: every deploy-and-verify path collects one diagnostic bundle on failure and classifies it into a one-line cause, closing the silent-502 gap.
- **Nightly dashboard `hop3-testlab` (ADR 044)**: run history, live progress, the regressions diff, and trends.
- **Privileged-operations daemon `rootd` (ADR 041)**: the operations that need root run through a small, audited daemon instead of sudoers.
- **App hostnames**: declare and manage an app's domains from `hop3.toml` and the CLI.
- **Cross-instance backup migration (ADR 024)**: restore a backup onto a different Hop3 server.
- **CLI ergonomics overhaul (ADR 036)**: space-separated commands, implicit app, sticky context, aliases, did-you-mean suggestions, categorized help, scriptable confirmations, secret inputs.
- **Nix integration**: hermetic builds from `hop3.nix`, starter app packages, Nix installer support.
- **Computed env variables**: `${VAR}` interpolation in `hop3.toml`.
- **WSGI auto-discovery**: detect Python entry points automatically.
- **Servers and project contexts (ADR 042)**: `hop3 server`, `hop3 context`.
- **Deploy preview and project-mismatch guard**.
- **Shared failure diagnosis**: every deploy collects a diagnostic bundle, classifying failures.
- **Nightly dashboard `hop3-testlab`**.
- **Privileged-operations daemon `rootd` (ADR 041)**.
- **App hostnames**: declare and manage domains from `hop3.toml` and CLI.
- **Cross-instance backup migration**.

### Changed

- **Command syntax (BREAKING, ADR 036)**: multi-word commands use spaces, not colons (`hop3 env set`, not `hop3 config:set`); the old colon form prints a migration hint.
- **Command names (BREAKING, ADR 036)**: user management moved under `user`, addon commands to the singular `addon`, and a few verbs were normalized.
- **Exit codes (ADR 036)**: the exit-code scheme was reorganized; scripts that branch on specific codes may need updating.
- **Server vs context vocabulary (BREAKING, ADR 042)**: the old global "context" is now a *server*. "Context" means a project deploy target; existing config is migrated on first run.
- **Testing layers (ADR 043)**: the test suite is three layers selected by speed tier; a plain `pytest` run never starts Docker.
- **More reliable deploys**: clearer messages about already-set env vars, IPv4 addon hosts to avoid IPv6 resolution issues, and assorted build and worker-precedence fixes.
- **Safer upgrades**: pending database migrations run on upgrade. An existing virtualenv is no longer replaced.
- **Containerized app database access**: addons are reachable from apps on any private Docker network.
- **Space-separated commands (BREAKING, ADR 036)**: `hop3 config set` not `hop3 config:set`.
- **Exit codes reorganized (ADR 036)**.
- **Server vs context vocabulary (BREAKING, ADR 042)**: existing config migrated on first run.
- **Testing layers (ADR 043)**: plain `pytest` never starts Docker.
- **Addons reachable from Docker apps** on any private network.

### Fixed

- Faster deploy log streaming.
- Addon connection fixes (MySQL, host resolution).
- `--why` now diagnostic-only; app name resolves from `hop3.toml`.

### Security

- Untrusted RPC arguments validated.
- Auth hardening; admin-takeover path closed.
- Addon credentials re-encrypted with automatic migration.
- Privilege boundary moved from sudoers to rootd (ADR 041).

## [0.4.0] - 2026-03-27

Major release: Hop3 becomes a complete self-hosted PaaS.

### Highlights

- Client-server architecture (CLI on laptop, server on host)
- Ten language toolchains (Python, Node, Ruby, Go, Rust, PHP, Java, Clojure, Elixir) + static sites
- Database addons (PostgreSQL, MySQL, Redis) with encrypted credentials
- Automatic Let's Encrypt SSL with auto-renewal
- Multi-distribution: Ubuntu, Debian, Fedora, Rocky Linux, AlmaLinux
- Config validation with helpful error messages
- Security audit with command-injection fixes
- Comprehensive test suite

### Security

- Command injection fixes across OS plugins and utilities.
- Session lifetime reduced to 24 hours.
- JWT secrets enforced to 32-byte minimum.
- Authentication bypass in middleware closed.

## [0.3.0] - 2025-03-24

- First stable version for simple Python WSGI and static sites.
- Core internal API for app lifecycles.
- Stabilized installation for production-like environments.

## [0.2.0] - 2024-06-28

- Modernized Nginx setup, actor-based framework, major documentation and test improvements.

## [0.1.0] - 2024-04-11

The initial release covers the core architecture, app builders, addon support, SQLAlchemy models and the first test runner.

[Unreleased]: https://github.com/abilian/hop3/compare/0.7.5...HEAD
[0.7.5]: https://github.com/abilian/hop3/compare/0.7.4...0.7.5
[0.7.4]: https://github.com/abilian/hop3/compare/0.7.3...0.7.4
[0.7.3]: https://github.com/abilian/hop3/compare/0.7.2...0.7.3
[0.7.2]: https://github.com/abilian/hop3/compare/0.7.1...0.7.2
[0.7.1]: https://github.com/abilian/hop3/compare/0.7.0...0.7.1
[0.7.0]: https://github.com/abilian/hop3/compare/0.6.2...0.7.0
[0.6.2]: https://github.com/abilian/hop3/compare/0.6.0...0.6.2
[0.6.1]: https://github.com/abilian/hop3/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/abilian/hop3/compare/0.5.0...0.6.0
[0.5.0]: https://github.com/abilian/hop3/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/abilian/hop3/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/abilian/hop3/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/abilian/hop3/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/abilian/hop3/releases/tag/v0.1.0
