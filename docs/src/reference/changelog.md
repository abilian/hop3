# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **A unit test rebuilt the operator's cloud server on every run.** `hop3-deploy-server` validated the `--docker` and `--provider` combination only *after* acting on `--provider`. A unit test of that check (added 2026-08-13) walked the path with `--provider hetzner`; on any machine whose shell exported `HETZNER_API_TOKEN` and `HETZNER_SERVER_ID`, every run of the installer unit suite sent a real `rebuild_server` for that server, waited for it, then passed. The dev box named by those variables was wiped on every `make test-fast` for four weeks before the pattern was seen in Hetzner's action log. Three changes, each sufficient alone: the deployer now validates every target word before it provisions anything; every pytest session strips `HETZNER_API_TOKEN`, `HCLOUD_TOKEN` and `HETZNER_SERVER_ID` the way it already strips the dev-host variables, so no test layer can hold a credential that rebuilds a machine; and a rebuild now refuses any server that does not carry the Hetzner label `hop3-throwaway=true`, which the operator sets once on the dedicated test server (`hcloud server add-label <id> hop3-throwaway=true`), so a wrong id in a config file or the environment can no longer reach a box anyone uses.

### Added

- **`[proxy]` lets an app declare what the reverse proxy will carry for it.** `client_max_body_size` was hardcoded at `50m` in the generated vhost, with no key for it anywhere in the recipe schema, so a file-upload app deployed green, health-checked green, and refused every upload over 50 MB: PeerTube cannot take a video, and a CDN cannot publish a release. Two typed keys now travel from `hop3.toml` through the build artifact to whichever proxy is active: `max-body-size` (a number with an optional `K`/`M`/`G`, or `0` for no limit) renders to nginx `client_max_body_size`, Caddy `request_body max_size`, or a Traefik `buffering` middleware; `request-buffering = false` renders to nginx `proxy_request_buffering off`, so a large upload streams through without being written to the proxy's disk in full before the app sees a byte. These are typed values, so the validation runs before anything reaches a template. A size with a `;` in it is refused at deploy and never spliced into the config, and the declaration carries over a proxy swap. Read from the artifact, so a restart that regenerates the vhost without rebuilding still gets the limits the app declared. Two proxies have limits of their own and say so: Caddy has no buffering switch (it streams already), and Traefik can only enforce a body limit through buffering, so an app asking for both gets the limit and a line in the deploy log.

- **Garage replaces MinIO as the object store behind the S3 addon.** MinIO withdrew its public server binaries (`dl.min.io` answers 410 for every server path and its GitHub releases carry no assets), so `hop3-install server --with s3` could not complete at all, and since a failing `--with` feature aborts the install, neither could the install. Garage is a single static musl binary, S3-compatible and AGPL, and it is now what the installer provides and what the addon talks to by default. Applications see no difference: they receive an endpoint and a key scoped to their own bucket, as before. `MinIOBackend` stays selectable with `HOP3_S3_BACKEND=minio` for an operator running their own MinIO; the installer no longer provides one. Existing MinIO data is untouched and is not migrated; the two are separate object stores. See ADR 060.

- **`hop3-backup-server` snapshots a server before an upgrade.** Run from your machine (`--host`, `--version` for the label, `--fetch DIR` to bring the snapshot home), it uploads the server-side script it ships with and runs it as root. The script copies the control-plane database consistently while the server runs, archives every config and secret file, the service units, the proxy and uWSGI trees and the apps tree, and dumps each backing service that is installed (PostgreSQL, MySQL, Redis; Docker volumes on request). Every step reports ok, skip or FAIL, the result carries checksums and a `RESTORE.md`, and a snapshot that says it finished is complete.

- **`hop3-restore-server` puts a server back to a snapshot.** The control-plane database, config and secrets, the apps tree, and the PostgreSQL, MySQL, Redis and Docker-volume dumps a snapshot holds; `--only` restores a subset, `--from-local` uploads a snapshot fetched earlier. It stops the server and the apps while it works, keeps a `.pre-restore` copy of everything it replaces, migrates the restored database to the installed code, and reports success only once the server answers. Both commands take `--ssh-option` for a ProxyJump or a private known_hosts, and both are proven end to end by a Docker e2e that deploys an app with data, snapshots it, destroys it, restores it and checks the data is back; the same test runs against a real box with `--ssh-host`.

- **HTTPS is the everyday transport; SSH is bootstrap and rescue.** Signing in over SSH used to record `ssh://root@host` as *the connection*, so every later `hop3 apps`, `hop3 logs` and `hop3 status` opened a root shell, once per invocation, to do read-only work, routing around the API's own authentication and rate limiting. A login now asks the server for its own public address (only the server knows how it is fronted) and records that as the everyday one, keeping the SSH target solely to mint a token, including renewing an expired one unattended. A server with no admin domain, an untrusted certificate, or one too old to answer keeps the tunnel, and the login **says which**, because the failure to avoid is an operator with a working CLI who never learns that every command opens a root shell. `--via-ssh` forces one command through the SSH route for when the everyday one is what broke, and refuses rather than falling back. Contexts carry both addresses, `hop3 context add --bootstrap` declares one, and the schema accepts `bootstrap` under the same no-credentials rule as `server`.

- **Every target the CLI can reach has a name.** `hop3 login` wrote an *unnamed* default target that `get_api_url` consults below every context. So an operator with any context configured was told the login succeeded and then had every command go somewhere else. There is no unnamed target now: a login with no `--context` records the reserved name `default`, and pointing that name at a *different* address without asking is refused rather than guessed at, because "I replaced my server" and "I have two now" are indistinguishable from the CLI's side. `default` is reserved against *project* contexts, which resolve first and would otherwise shadow it for everyone in a checkout. `HOP3_API_URL` / `HOP3_DEV_MODE` stop being a parallel resolution system and become the context named `env`: listed by `hop3 context`, named in the warning before a destructive command, and no longer needing a special case in every place that reports where a command is going. A one-shot migration names an existing unnamed target, collapses the two keys that both meant "which context is current", reports every outcome including the two that drop something, and aborts rather than guessing on the one shape it cannot resolve.

- **The login surface names one axis: which client gets a credential.** `--ssh` named a transport and `--web` a destination, so they read as alternatives on one axis while sitting on two. Both travel over SSH regardless, which is why repeating `root@host` in each made them look like a pair. The target is positional (`hop3 login root@server`), `--browser` says the credential is for the browser and takes an *optional* target, and the login prints one line naming the user, the address and the context. Both old spellings still dispatch.

### Fixed

- **An app that answered every request was reported as an app nobody was behind.** With `[healthcheck].contains` the readiness gate wants a body, so an app can serve perfectly and still never be declared ready. The failure path inferred its diagnosis from the port alone and said "the server bound its socket but no worker is serving (the worker failed to boot, or is hung)", then advised a longer deadline. invoice-ninja-nix answered 173 probe requests in the 100 seconds before its deadline, each logged by Laravel, each in ~0s, and was described as a dead socket. The failure path now asks the app once more before it speaks: when the app answers, it names the path it probed, the status that came back, the marker that did not match and the first 200 characters of what was served instead, and says that a longer deadline cannot help. The old wording is kept for the case where it is true: nothing answered.

- **A check that passed at the end of the deploy failed when the harness ran it, on the same app, in the same minute.** Two things run an app's `check.py`: the deploy's own smoke test, which passes the app's whole runtime environment, and hop3-testing, which uploads the script and runs it on the server. The second read the encrypted credential store and exported `HOP3_ADMIN_*` and nothing else, so `Check.has_probe` was false for every app it tested and every check silently fell back to the operator's credential, the weaker claim, taken without saying so. Piwigo turned weaker into wrong: on an empty gallery it answers an onboarding interstitial to a guest *or an administrator* on every page, and to an ordinary user, which the probe is, it does not. Which credentials a check may see is now one function on the server (`check_credentials`), and both runners read it. The probe credential also stops being inherited from the server process's own environment, where an ambient `HOP3_PROBE_PASSWORD` would have posed as every app's probe.

- **The pnpm a server built with was whatever npm's `latest` tag pointed at that day.** The installer ran `npm install -g pnpm`, unpinned, and skipped it entirely whenever any pnpm was already present. So two servers of the same Hop3 version built the same app differently, and the version kept moving under a deployed app with no change to the app, the recipe, or Hop3. Etherpad absorbed three breaking pnpm changes this way, two of them patched into its own download script. The third could not be: pnpm 12 removed `pnpm list --no-production`, which Etherpad's plugin migration runs at every boot, so the build passed and the app died four seconds into startup on a box whose pnpm had rolled from 11 to 12 between catalog runs. The installer now pins an exact version, reconciles it on every run rather than skipping, and says so out loud when another pnpm is ahead of it on `PATH`.

- **The readiness probe did not identify itself, and some apps refuse an anonymous client.** `http.client` sends no `User-Agent` unless asked, and every other HTTP client Hop3 has said who it was (`hop3-fetch`, `hop3-ping/1.0`); the one gating every deploy did not. GoToSocial answers `418 I'm a teapot` to any request without one, a common bot filter, so its `[healthcheck].contains` could never match: both the native and the Docker variant failed a catalog run after sixty seconds of polling while serving the harness's `curl` on the same path. The probe now sends `hop3-healthcheck`.

- **A deploy that timed out said nothing about the port the app had actually bound.** Ignoring `$PORT` is the commonest deploy failure there is: Grafana binds 3000 unless `GF_SERVER_HTTP_PORT` says otherwise, and the app starts cleanly, logs "HTTP Server Listen", and is invisible to both the probe and the proxy. The platform reported "did not respond to health checks within 60.0s" and advised a longer deadline, the one remedy that cannot work for an app that is already up. The failure now reads the app's own sockets out of `/proc/net/tcp{,6}` and `/proc/<pid>/fd` and names them: which port was assigned, which are held, and that `[run].start` is where `$PORT` belongs. No `ss`, no `lsof`, no new dependency.

- **`${VAR}` in a literal `[env]` value was silently exported as those characters.** Grafana's recipe asked for `GF_DATABASE_HOST = "${PGHOST}:${PGPORT}"` and `GF_SERVER_HTTP_PORT = "${PORT:-8080}"` under `[env]`, which does not interpolate; the app received the templates verbatim, fell back to SQLite and to its own port 3000, and the PostgreSQL addon Hop3 had provisioned for it sat empty while the proxy pointed at a port nothing bound. Every step reported success until the readiness gate lapsed. Three sections behave differently and now say so: `[env]` is literal and rejects a `${...}` at validation (so `hop3check` catches it before a deploy), naming which of the three the value wants; `[env.computed]` interpolates and now **fails the deploy** on a reference the app does not have, listing what is available, instead of warning and storing the template; and `$PORT`, allocated after both are resolved, belongs in `[run].start`. Three recipes in the catalog were relying on the old silence.

- **Deploys were randomly refused for an nginx reload that had worked.** rootd verifies a reload by watching for a worker process forked at or after the moment it sampled `/proc/uptime`. The sample is seconds with two decimals and a worker's `starttime` is an integer tick count, so the reference has to be compared at tick resolution, and multiplying the parsed float by 100 does not land on the integer. `81408.99 * 100` is `8140899.000000001`, a hair above the tick a worker forking in that same centisecond reports, so the `>=` test rejected a worker that was genuinely fresh. Nothing else qualified, the fifteen-second budget lapsed, and the deploy was aborted with "nginx kept the previous config" for a reload that had applied perfectly. It depends on the exact uptime value at that instant, so it struck at random and never twice in the same place: `74444.56 * 100` is exactly `7444456.0` and behaves. The reference is floored to whole ticks now, which can only ever make it one tick early. Safe, because a pre-existing worker would have to have forked inside the same centisecond to be mistaken for a fresh one.

- **A failed nginx reload reported a conclusion instead of its evidence.** "No fresh worker processes appeared within 15s" looks the same whether nginx forked nothing, forked a worker the check failed to see, or logged its rejection somewhere the check cannot read. The third is the normal case in a container, where nginx runs with `daemon off`, logs to stderr, and leaves `/var/log/nginx/error.log` empty. That silently disables the discriminator between "rejected" and "merely slow", so every failure takes the long path and then says nothing useful about which it was. The message now carries what was measured: the reload's reference tick, the start times of every nginx worker actually seen, and whether the error log was readable and by how much it grew, so the next occurrence is diagnosable from the message alone, even after the box is gone.

- **`hop3 run` killed long commands at five minutes and showed nothing until they ended.** A weekly maintenance job that legitimately runs longer came back as `HTTPConnectionPool(host='localhost', port=61455): Read timed out. (read timeout=300.0)`, a message naming a tunnel port rather than the job, for a job that was working. The command ran inline on the request, captured everything, and returned it at the end, so until it finished there was nothing to look at and a job that was progressing looked exactly like one that was wedged. It now runs in a worker thread and streams its output over the same SSE channel a deploy uses: lines appear as the program prints them, stderr interleaved in the order it was written, and there is no timeout at all: the operator asked for the job, and killing it at an arbitrary deadline loses the work while explaining nothing. `PYTHONUNBUFFERED` is forced on the child, because a Python program writing to a pipe block-buffers by default and its output would otherwise arrive only at exit. A failing command still surfaces its output and, when it printed nothing, says so rather than showing a bare exit code.

- **A streamed job that was not a deploy still reported "App deployed successfully".** Both share the SSE path, so a one-off command finished by claiming a deployment that never happened. The completion event carries what to say, and a deploy keeps the exact phrase the tutorials and the non-streaming path assert on.

- **A stream was dropped an hour after it started, even while still being written.** Expiry by age was safe when only deploys streamed, since a deploy is bounded by its own build; a `hop3 run` is bounded by nothing. Only finished streams are collected now, and the replay buffer has a ceiling so one chatty long-running job cannot grow the server's memory without limit.

- **Readiness assumed every backend speaks HTTP.** A deploy may only report success once the app answers on its port. A bound socket is not proof, because a master binds before forking and accepts connections while every worker is dead. That gate opened a plain HTTP connection, which no php-fpm pool can answer. A backend now declares its protocol in the build artifact and is probed with a matching client: FastCGI backends are asked for the pool's `ping.path`, which is answered by a pool child and so carries the same evidence the HTTP probe was written to demand. The proxy reads the same field, so the two cannot disagree about what an app is. Nothing changes for an HTTP backend, or for an app deployed before the field existed. See `notes/readiness-and-non-http-backends.md`; the standing answer is a process manager that reports readiness instead of being probed for it (ADR 023).

- **A vhost the proxy refused stayed in its include directory and broke every later deploy.** `nginx -t` validates the whole tree, so an app's candidate config has to be written before it can be judged, and when the answer was no it was left there. From that point every validation read the same directory: the next app's deploy aborted, and so did every certificate renewal, on a file belonging to an app neither of them named. One app could take the deployment down with a bad config. A proxy config is now written and validated as one operation (all three proxies, not just nginx): a rejected one is rolled back to the content the running proxy still has loaded, and parked as `<app>.conf.rejected`, outside the `*.conf` include glob, so nothing reads it, and named in the diagnosis so the operator can still see what was generated. A later success clears it, and destroying the app removes it. A failed *reload* is deliberately excluded: nginx forks its workers asynchronously, so a reload reported as failed may have been slow rather than refused and already applied, and rolling back there would leave the file disagreeing with what nginx is serving. A validated config costs nothing on disk, since it passes `nginx -t`, and the next reload picks it up.

- **Caddy and Traefik deployed configs they had not managed to check.** Caddy warned and carried on when `caddy validate` could not run at all (binary absent, check timed out), and Traefik did the same for anything that was not a YAML error, so a deploy could report success having validated nothing. Both abort with a `Diagnosis` now, naming the rejected file, as nginx already did. Traefik's "PyYAML not installed, skipping config validation" branch is gone: `import yaml` is at module top and pyyaml is a hard dependency, so the module could not have loaded to reach it.

- **`--help` and `--version` after a `run` program were answered by hop3.** `hop3 run mycli sub --help` printed the help for `hop3 run` and the program never saw the flag: `handle_help_flags` searched the whole of argv, while `parse_flags` had always stopped consuming global flags at the program token. Two passes over one argv, one boundary, and only one of them knew about it. The boundary is stated once now, and a test asserts the two agree.

- **A failed SSH bootstrap is diagnosed by Hop3, not by `su`.** Every bootstrap operation wraps its remote call in `su - hop3 -c …`, which only root can do, so connecting as an ordinary admin account failed with `su: Authentication failure`, naming neither the command that ran nor the requirement it broke. The four operations shared one copied error path; they now share one *helper*, which reports the input, the command and its output and, when the SSH user is not root, the requirement and the way forward. `hop3@host` is refused before dialling: that account's key carries a forced command, so the remote line could never have worked.

- **The warning before a destructive command names the server.** It printed the context *name*, which every single-server install spells the same way, and printed nothing at all after `hop3 login --context prod` because the reader consulted a different key from the resolver. It now names the resolved address and the context it came from.

- **The deployer configured the local CLI through a deprecated command whose warning it discarded.** `hop3 settings set server` writes `api_url`, which `get_api_url` consults *last*, below every context. So "CLI configured to connect to <host>" was followed by commands going elsewhere. It writes a real context now, and the success line reports the outcome it got instead of being printed unconditionally after a failed token fetch.

- **The docs CLI linter called the built-in short forms deprecated.** `hop3 apps`, `hop3 login`, `hop3 logout` and `ssh` are the deliberate short-form surface (ADR 036 D9), not a rename's leftovers, but the linter merged them with the server-side legacy spellings and told readers their daily commands were obsolete. It also swallowed a trailing shell comment into the command it reported.

- **The deployer no longer ends by naming a command that does not exist.** Its completion banner offered `hop3 admin set-password` to rotate the generated admin password; there is no such command. The banner now gives the one command that actually signs the operator in, `hop3 login root@<host>`, which needs no password because SSH access to the server is the credential. It also says that the password it is hiding opens nothing on its own, with `hop3 user set-password <user> --stdin` for setting one you know.

- **An unknown command is reported by what you typed, not by its first word.** `hop3 admin set-password` failed with "Command 'admin' not found" and suggested `domain`, `domains`, `addon`; the dispatcher had thrown away every token after the first, so the suggestion was computed against `admin` alone. The server now walks the command tree as far as it goes and names the token that broke the walk, so the same mistake answers "Command 'admin set-password' not found. Did you mean: 'user set-password'?".

- **There is one page that tells a new operator how to get in.** Nothing did. The material was spread over the server-setup page, the CLI reference and a blog post, led with `hop3 init` (which the CLI's own help says you no longer need), disagreed with itself on where the token is stored and how long it lasts, and never once said that the CLI and the web dashboard hold *different* credentials. `Signing In` (Get Started) now states the model in one table, gives the one command that signs the CLI in, says why the dashboard is a second credential and why it needs HTTPS, and ends with a symptom-to-fix table. The deploy banner, `hop3 login --help` and the dashboard's own login page all tell the same story.

- **`hop3 login --ssh` and `--web` no longer read as a pair.** They are not one: `--ssh` names a transport, `--web` names a destination and travels over SSH as well, and only the first is a login; the second prints a URL to open. Every place that offered them as two bullets (the deploy banner, the login help, the docs) now gives the one command that has to be run and describes the dashboard link after it, saying outright that it is not the alternative to `--ssh`. The flag names themselves are unchanged.

- **`hop3 login --help` never mentioned `--web`.** The command has dispatched on it since magic links landed, so the only passwordless way into the web dashboard was undiscoverable from the CLI that implements it. The help now covers both surfaces, `--context`, and the password-reset path that does not need the password.

- **The web dashboard's login page offers no password to the operator who has none.** The generated admin password is never shown in the clear, so the first visitor arrives at a form they cannot fill. The page now names the passwordless way in, `hop3 login --web root@<server>`, under the form, with the server's own configured admin domain filled in.

- **The CLI reference claimed API tokens last 30 days.** They last 24 hours (`HOP3_TOKEN_EXPIRY_HOURS`); the 14-day figure belongs to the web session, which is a different credential. The server-setup page also said `hop3 init` writes the token to `config.toml`, which has not been true since tokens moved to the secret-free credential store.

- **The CLI teaches one name for itself.** Help output, the unknown-command hint and the command docstrings said `hop` while every document, tutorial and error message around them said `hop3`. Both entry points still work; the text now uses `hop3` throughout.

- **Uploads to a server on a non-standard SSH port work.** The deployer passed ssh's `-p PORT` to scp as well, which reads `-p` as "preserve times" and took the port number for a file; every `scp` to such a server failed while the ssh commands around it worked.
- **An in-place server upgrade now upgrades rootd and the client too, and proves what it installed.** Every update path of `hop3-deploy-server` installed `hop3-server` alone, so `hop3-rootd` and `hop3-cli` stayed at the old version beside the new server. The 0.7.3 server calls a daemon op that a 0.6.2 rootd does not have, so the first PostgreSQL addon change after such an upgrade would have failed with "no such op", far from the upgrade that caused it. The three packages are now installed at one version from the same source (a pinned PyPI release, a git ref, or the local checkout), the venv is checked to hold exactly one version before the migrations run, rootd is restarted before the server, and the revert hint names all three.
- **A `--from local` update on the Docker backend reinstalled the old code with a green message.** `docker cp` copies a directory *into* an existing destination, so the second upload of the server tree nested the new one inside the old one and `pip install /tmp/hop3-server` reinstalled the old tree; the deployer then reported "Migrations applied" and "Local code deployed" with the old version still running. The upload now replaces the destination, and the version check above catches the case regardless.
- **The Docker backend's update path failed on a container created by an older deployer.** Its supervisor setup chowned the download-cache mountpoint, which a container the 0.6.2 deployer had created did not have; the directory is created first.
- **`hop3-test upgrade-chain` was passing without upgrading anything.** The chain installs an old release by running that release's own deployer from a worktree of its tag. The deployer was renamed at 0.7.0, the harness asked every worktree for the new name, and `uv run` answered a missing script by falling through to `PATH`, where the developer's current deployer was. A "fresh 0.6.2 install" therefore installed the current version and the "upgrade" reinstalled it over itself. The harness now reads the script name from each checkout, syncs the checkout's environment before running it, refuses to run when the script is not there, and asserts after every hop that the installed version is the one the hop claims. It also pins each worktree to the interpreter the harness runs on, since a tag's worktree carries no `.python-version` of its own and the newest interpreter on a machine may have no wheel for a dependency.
- **The administration guide no longer presents the single-file installer as the upgrade path.** Re-running it on an existing server does not migrate the schema, does not upgrade the code unless a version is pinned, and restarts the uWSGI emperor, which restarts every app. The guide now documents the `hop3-deploy-server` sequence, the rootd step, and the snapshot to take first.

## [0.7.3] - 2026/09/08

### Added

- **`hop3 app shell` opens a shell inside a deployed app.** It runs with the environment the app's own workers get: the toolchain's `PATH` and variables from the build artifact, the addon credentials, `PORT`, and the app's source directory as the working directory. The session goes over `ssh -t` as the `hop3` user through the forced command that already serves `git push`, so nothing new listens on the server. A pty when stdin is a terminal, plain pipes otherwise, so `echo cmd | hop3 app shell` can be scripted. The shell's exit status is the session's. An app that does not exist, was never deployed, or runs under docker-compose is refused with a reason. `hop3 ssh` is an alias. `hop3 run` was fixed on the way: it built its environment without the build artifact, so a Nix app's store binaries were not on its `PATH`; it now shares the workers' environment builder.

- **`hop3 env set` takes secrets without putting them on the command line.** `KEY=-` reads the value from stdin, `KEY=@path` from a file, and a bare `KEY` prompts with echo off, so the value never appears in the shell history or in `ps`. A value that really starts with `@`, or really is `-`, is written `@@…` or `--`. The command's own output is redacted, including the previous value it reports on an overwrite, which used to print the old secret in clear. (ADR 036)

- **`hop3` answers help and did-you-mean without a server.** `hop3 help` and `hop3 help <command>` work before `hop3 login`, from a command list the client refreshes at every successful login. A mistyped command gets a suggestion the server computes from what you typed and what was valid at that point, carried as data on the error; the client no longer scrapes the error's wording. `hop3 help --all --json` emits the whole command tree as JSON.

- **One SSH configuration for everything the CLI spawns.** The RPC tunnel, `hop3 tunnel`, `hop3 app shell` and the `hop3 login --ssh` bootstrap read the same `ssh_key`, `ssh_port` and new `ssh_options` settings (`HOP3_SSH_KEY`, `HOP3_SSH_PORT`, `HOP3_SSH_OPTIONS`). A port in the target (`root@host:2222`) is honoured everywhere. `ssh_options` takes extra `-o` values: a `ProxyJump`, a private `UserKnownHostsFile`. Until now `login --ssh` ran a bare `ssh user@host`, so a server on a non-standard port answered through the tunnel while the login that sets that tunnel up could not reach it.

- **`[admin].verify` and `[probe].verify` prove a bootstrap account exists.** A zero exit from `create` is not evidence: Gitea and Forgejo reject the reserved name `admin` by printing an error and exiting 0, which once had Hop3 hand an operator a password for an account that was never made. With `verify` declared, the command runs after `create` and must succeed before the credential is marked bootstrapped. Without it, the deploy log says the command ran and claims nothing more.

- **`hop3-tui` is rewritten on turbodesk and reaches `ssh://` servers.** It takes the server and token from hop3-cli by asking hop3-cli, contexts and tunnel included, so the two clients can no longer disagree about which server they talk to. It gained a command line (`--server`, `--token`, `--version`, and a `--help` that lists the key bindings) and a help dialog with each screen's own keys. Its commands, `--app` flag and response handling were realigned with the server, pinned by a Docker e2e that exercises the client and server contract.

- **The documentation build produces `llms.txt` and `llms-full.txt`**, an index and a single-file rendering of the documentation for language-model readers.

- **PHP applications get a production runtime.** Ten catalog applications served through PHP's built-in single-threaded server or `artisan serve`; requests serialize, and Nextcloud and Matomo issue concurrent internal sub-requests, so they deadlock against their own only worker. The PHP toolchain now builds a php-fpm pool and runs it as a uWSGI `attach-daemon`, so the Emperor stays the only process manager on the box and the pool dies with the app instead of outliving it. nginx speaks FastCGI to it, serving the front-controller directory rather than the project root (`public/`, `web/` or `htdocs/` when one holds the `index.php`), which keeps `.env` and the vendor tree off the web, and `PHP_DOCUMENT_ROOT` overrides it. A request for a `.php` file that does not exist is refused rather than handed to the front controller. A recipe that still declares its own `[run] start` keeps it and keeps serving HTTP, so the migration is one line per recipe.

### Changed

- **PostgreSQL, Caddy and Traefik are reloaded through rootd.** Three call sites ran `sudo -n systemctl reload <service>` from the unprivileged deployer, which fails on any host where the `hop3` user has no passwordless sudo. The PostgreSQL one also threw the result away, so a rewritten `pg_hba.conf` that was never applied looked exactly like one that was; Docker apps then failed with `Host 'x' is not allowed`. A new `service.reload` daemon operation, allow-listed to the services Hop3 configures, handles it under systemd or supervisor.

- **JSON-RPC errors carry JSON-RPC codes.** A malformed request body got an HTML 500 no client could parse. The method check was an `assert`. The endpoint now answers -32600, -32601 and -32602 for a bad envelope, -32001 for unauthenticated, -32002 for rate-limited, and -32603 for a command that failed while doing its work, which used to be reported as "invalid params" whether the cause was a full disk or a dead subprocess.

- **RPC commands and dashboard actions run off the event loop.** The server runs a single worker. A command, or a restart, stop or backup clicked in the dashboard, ran inline on it, so a multi-minute deploy froze authentication, the dashboard and every streaming deploy log for its duration. They now run in a thread, one command at a time as before.

### Security

- **Stopping or destroying an app can no longer remove another app's worker configuration.** The worker files of app `wiki` were swept with the pattern `wiki*.ini`, which also matched `wiki-js_web.1.ini`, so destroying one app ripped the configuration out from under an unrelated one; the leftover showed up as an order-dependent failure in whatever was deployed next. The sweep now stops at the app-name boundary, at all eight sites.

- **A symlink inside an app's tree can no longer point a backup or a volume outside it.** The containment check for `[backup].paths` and `[[volumes]]` compared paths lexically, so `src/data -> /etc` counted as inside the tree and would have been read, seeded or deleted through. Both sides are resolved before comparison, and a regression test tries to escape.

- **Login failures are indistinguishable, including in time.** An unknown username answered faster than a wrong password, because a real user's hash was verified with bcrypt while an unknown one returned before any hashing. A disabled account had its own message. All three now get one message and the same bcrypt cost, so the response no longer says whether an account exists (CWE-204).

- **A builder's refusal reaches you.** A builder that refused a misconfigured app (the Nix builder, for an app carrying both `hop3.nix` and `[nix].template`) had its refusal swallowed as "this builder does not apply", so the next builder in line built the app the wrong way. The refusal now stops the deploy with its message. Plugins are also registered under their own name, so two plugins claiming one identity fail at startup. A hook implementation whose specification no longer exists is an error, where it used to be a permanent no-op.

- **The PostgreSQL addon refuses a name that would give PostgreSQL a reserved role.** An addon named `pg-…` derived the role `pg_…`, which PostgreSQL reserves, so the server rejected it after the database had been created. It is refused up front, naming the addon name that caused it.

### Fixed

- **A deploy no longer fails because nginx took more than two seconds to reload.** rootd verifies a reload by watching for new worker processes, since `nginx -s reload` returns 0 whether or not the configuration was accepted. The check gave nginx two seconds. On a busy host a reload nginx had accepted forked its workers later than that, so the deploy was refused with "did not apply the new config" for a configuration that was fine. A rejected reload logs `[emerg]` at once and an accepted one logs nothing, so the check now fails immediately on a logged error and otherwise waits up to fifteen seconds.

- **`--with nix` either installs Nix or stops the install.** A failed Nix install printed a warning and reported success, so every Nix app on that server failed to build later. The installer also never installed `xz`, which the Nix installer needs and a bare Ubuntu 24.04 does not have.

- **A restart against a garbage-collected Nix closure is refused for static sites too.** The guard that refuses to start a Nix app whose store paths were collected ran only for artifacts of kind `nix`. A Nix-built static site is a `static` artifact, so for that case the guard returned before looking and the restart reported success over missing files. It now gates on the builder and counts the artifact's own store path as a root.

- **`hop3 run … python -c "…"` no longer loses `-c` to `--context`.** Global flags were parsed anywhere in argv, so a flag meant for the program was taken by the CLI and the command failed on an unknown context. Flag parsing stops at the program for `run` and `app run`, and at a POSIX `--` for every command.

- **`hop3 app destroy <name>` no longer asks you to confirm the wrong app.** A stray positional was rejected only after the confirmation prompt, which had already named the app resolved from the current directory, so `hop3 app destroy other-app` inside a project asked you to type the project's app name. The positional is refused before anything is asked; the app is always `--app`.

- **`hop3 app logs --help` reaches the same server as `hop3 app logs`.** Commands that need no authentication skipped context resolution and fell through to the legacy default server, which could be a retired one, while the command itself went to the default context's server.

- **A reset tunneled request says why.** Over `ssh -L`, the client only sees a connection reset when ssh cannot open the channel; the reason is on ssh's stderr. The error now carries it. On "connect failed" it adds that the tunnel is up but nothing answers on the remote port.

- **The shell-completion cache survives a crash mid-write.** An interrupted write left a NUL-padded file that read as an empty command list, so suggestions and completion silently did nothing, for months on one machine. The cache is now written atomically with fsync and honours `HOP3_CONFIG_DIR` like the configuration does.

- **`hop3.toml` accepts `[cli]`.** The CLI reads `[cli].app` as one of its app-resolution sources, but the schema forbade the section, so a project following the CLI README was rejected at deploy. The schema now also documents what `[env]` takes: a scalar, `generate`, `ref`, and the `[env.computed]` table.

- **Dashboard actions report their failure.** A restart, stop or backup that failed printed the error to the server's stdout and redirected to a page saying only "failed"; the page now shows the error. An app whose `Procfile` or `hop3.toml` could not be read was rendered as "no workers"; it now shows the parse error.

- **`hop3-server plugins` reports a broken plugin instead of dropping it.** A plugin that raised while being listed vanished from the capability listing with nothing said, turning a plugin bug into "that feature does not exist".

- **Two apps can no longer share a name.** `app.name` is unique in the database and `image_tag` is NOT NULL. The migration aborts, naming the duplicates, if a database already holds two apps of the same name: each duplicate owned its own env vars and addon credentials, while every lookup by name raised once a second row existed.

- **hop3-test and the Docker e2e suite test what they claim.** The main deploy suite pointed at fixture directories renamed long ago, collected zero tests and reported "1 skipped"; it now runs 22 fixture deploys and a missing fixture directory is an error. The test runner installs the backing services the test apps declare instead of expecting `--with` by hand. Eighteen e2e tests that skipped on a default run now run: Nix in the image and on the target, PostgreSQL backups and restores, archive integrity, and the SSH transport including `hop3 login --ssh` and `app shell`. A sanitized `DOCKER_CONFIG` that had lost its `contexts/` directory, so `docker` failed under OrbStack, Colima and Docker Desktop with "Docker is not available", keeps it. The tests keep their known_hosts in a private file of their own, away from the developer's.

## [0.7.2] - 2026/08/30

### Added

- **The catalog says how well it knows each app.** Every recipe now carries a maturity status: `golden` (installed, and signed into through the app's own login with the credential Hop3 generated), `beta` (deploys and serves its own content, sign-in not yet proven), and `alpha` / `broken` / `retired`, which are kept but never offered. Only the first two ship, so an app nobody has verified can no longer be installed by accident, and one that is known not to work keeps its recorded reason instead of disappearing. The catalog you fetch gains a `status` field per app; nothing else about its shape changes.

- **The catalog lists one entry per application, with its other build paths behind it.** An application packaged several ways used to appear once per packaging, so twenty applications filled fifty-five slots and `bookstack`, `bookstack-nix` and `bookstack-nixgen` competed with one another in search and for a place on the front page. The application now appears once, at the build path with the most evidence behind it, and names its alternatives on its own page. Nothing was withdrawn: every variant keeps its id, stays installable by it, and is still listed by `hop3 catalog list`.

- **The application gallery is live at `apps.hop3.cloud`.** The catalog has a public face: a page per application with its screenshots and readme, category and tag pages, and a search index that runs in the browser. It is generated by a new package, `hop3-marketplace`, which owns no description of an application at all: it imports the server's own catalog loader and taxonomy, so the public site and the dashboard on your server cannot disagree about what an app is.

- **An entry that would look unfinished can no longer be published.** `hop3-tools catalog lint` asserts what an operator sees before deciding to install: a title, description and version, a category from the known taxonomy, tags, a memory estimate, an icon and at least one screenshot, and refuses two entries claiming the same id, which used to make one of them vanish with nothing logged. It runs as part of building the catalog, so a bad entry cannot be signed.

### Security

- **Addon passwords are no longer briefly world-readable while being written.** Hop3 keeps each addon's password in a file only its own account can read. It got there the long way: the file was created with the usual permissions, the password written into it, and only then locked down. So for the length of every write, and again on every rotation, any account on the server could read it. It is now created locked down. The same change fixes a way to lose a password outright: writing the file emptied it first, so a write that failed part-way left no password at all while the database went on expecting the old one, and the app could not reconnect. Affects PostgreSQL, MySQL, Redis and email addons.
- **Two Redis addons can no longer be handed the same database.** Each addon gets one of Redis's fifteen numbered databases, but the number was picked and then written down three Redis round trips later, so two `hop3 addon redis create` calls close together could both take the same one and silently share each other's keys. The number is now claimed and recorded in a single step. A create that fails afterwards gives its number back rather than holding it forever, and when all fifteen really are in use the error says which addon holds each.
- **Deploys no longer build all at once.** Each deploy used to get its own thread the moment it was asked for, so ten `hop3 deploy` calls became ten simultaneous builds competing for the CPU, memory and disk of the server that is also running your apps. Builds now run two at a time (`MAX_CONCURRENT_BUILDS`) and the rest queue, saying so in their own output and starting on their own. Past 32 waiting (`MAX_WAITING_BUILDS`) a deploy is refused with a message rather than queued.
- **`hop3 app create <repo_url>` now checks the URL and bounds the clone.** The URL went to `git clone` as it arrived, and a URL is not an inert string to git: `ext::sh -c …` runs its argument, `file:///…` reads any path the server can, and a value starting with `-` is an option rather than an address. Hop3 now accepts `https://`, `http://`, `ssh://`, `git://` and the `git@host:user/repo.git` form, and refuses the rest by name. The clone itself is shallow, single-branch, and stops at 10 minutes or 2 GiB, so a repository chosen by one account can no longer fill the disk and take every app on the host down with it. A clone that fails or is stopped leaves nothing behind, including the app row, which a failed create used to keep.

### Fixed

- **Catalog entries showed almost nothing they declared.** `catalog.toml` was never read by the server: the loader asked for fields the recipes do not use, so all fifty-five entries loaded without tags, a memory estimate, services, an icon, or more than one category between them. The dashboard compounded it, reading three field names the model has never defined (Jinja renders those blank) and comparing a resource tier against a vocabulary the model cannot produce, so every app was styled heavy and the tier filter matched nothing. Both front ends now describe an application identically, and a test checks every field a catalog template names against the model that has to supply it.

- **An app whose front page redirects is no longer reported as failing to start.** A deploy is only healthy once the app serves its own content (`[healthcheck].contains`), but the check read the first response and stopped, and for an app that redirects `/` somewhere else, that response has no body. Kanboard and Invoice Ninja could therefore never satisfy a content check they demonstrably passed in a browser, and the deploy failed at the timeout with advice to raise it. The check now follows the app's own redirects, up to five, and never off to another host.
- **A comment in a Nix recipe could stop the app from starting.** Config files are written at startup by a shell that expands `${VAR}`, which is wanted, and ran anything in backticks, which was not. A recipe explaining itself in ordinary prose ("`http://localhost`, `/` bounced…") had those fragments executed as commands: the app died at boot with `No such file or directory`, having built perfectly. Backticks in config content are now text. Four bundled recipes were carrying this, one of them a comment containing a command that generates a key.
- **The terminal UI showed made-up logs and made-up system metrics.** Opening an app's logs in `hop3-tui` displayed eight invented lines, including `[ERROR] Failed to connect to redis` for an app that was fine, and added another invented line every few seconds so the pane looked live. It never asked the server for anything, and pressing `d` saved those invented lines to a file. It now shows your app's actual logs, and says so when there are none, when no app is selected, or when the server could not be reached. The system screen was the same story: CPU 42%, memory 63% and disk 81% were fixed numbers dressed up as live readings, the host was always `hop3.dev` running `v0.5.0`, and the service list always showed nginx, supervisor, PostgreSQL and Redis as running whatever their real state. Those panels now say the server has not reported a value, which is true, until the reporting is built.
- **`hop3-test` could not run an app's smoke test at all.** It handed the check a plain-HTTP port while the check has spoken HTTPS for some time, so every app reported the same thing: a TLS handshake against a cleartext port, surfaced as "the admin credential signs in" failing, which points at the credential and the app rather than at the harness. Three further faults were stacked behind it: a check's helper scripts were not uploaded, a probe was given a hostname only the server's proxy knows, and one lost the app's own `node_modules`. The same check now behaves identically whether a deploy runs it or the harness does.
- **`--keep` said it had destroyed the app it kept.** A failed test always printed "app destroyed after failure", including when `--keep` had deliberately left it running for inspection, sending you to a static bundle while the app itself was up.
- **A failed host-key scan in `hop3-test` said nothing.** Adding a server's SSH key discarded the error, so a scan that timed out looked the same as one that never ran. It now says which host it could not read and why.
- **A signing key too short to sign with is now refused.** `HOP3_SECRET_KEY` shorter than 32 bytes weakens every token the server issues (RFC 7518 §3.2). PyJWT warned and signed anyway, into a log nobody reads. Hop3 now stops with the length it found, the command to generate a good key, and the three places it looks, plus the warning that replacing it signs everyone out.
- **`APP_START_TIMEOUT` now does something.** The reconciler was constructed without it and kept its hardcoded 60 seconds, so an operator raising the setting changed nothing and a slow-starting app could be marked failed while it was still coming up.
- **Forgejo's licence is `GPL-3.0-or-later`, not `MIT`.** Forgejo relicensed at v9.0 and we package v14; the recipe still carried the pre-v9 value. Mattermost stays `MIT`, which is right for the compiled binary Mattermost, Inc. publishes and is now documented in the recipe so it does not get "corrected" to AGPL-3.0.

- **A truncated download was cached and reused as if it were complete.** `hop3-fetch` wrote whatever arrived and treated a short read as a finished file, so a connection cut mid-transfer poisoned the cache: every later build reused the partial archive and failed somewhere further on, where the cause was no longer visible. The size received is now checked against the size the server declared, and a mismatch is a failure. `hop3-fetch --refresh <url>` re-fetches an entry already cached this way.

- **A pinned dependency hash in a generated Nix recipe could mean different things on different machines.** For applications fetched with pnpm, the fetcher normalised the store's key order and timestamps and nothing else, so the file permissions pnpm happened to create made it into the output. A hash recorded on one machine then failed on another with an identical lockfile and an identical set of packages, which is what a catalog install of Vikunja hit, having reproduced perfectly where it was recorded. Recipes can now ask for the normalisation nixpkgs added later (`node-pnpm-fetcher-version`), and the pin that supplies it travels with them.

- **Python packages with Rust extensions could not be built under Nix at all.** The build derivation is sandboxed and offline, so cargo died reaching for crates.io. Their crates are now vendored during the fetch step, which is the one place with network access. Gradle applications and PHP applications had a gap each in the same generator: the Gradle dependency cache was not resolvable from inside nixpkgs, and PHP applications served through the built-in server ran single-threaded, so an application that called itself during setup (an installer, a first-run wizard) deadlocked against its own only worker.

- **A deploy could report success for an app whose background worker never ran.** A worker whose command is missing dies the instant it is spawned and is respawned to die again, but the process manager only announces the throttling several cycles in, so whether the deploy passed depended on how busy the box was. On an idle server the same broken app passed, and Hop3 reported success for an app with a dead queue behind a login page that rendered perfectly. A worker that cannot be executed now fails the deploy and says so. Separately, a worker declared as a bare command could not be found in a Nix app, because the spawner rebuilt its search path from a virtualenv shape a Nix artifact does not have; the artifact's own path is now kept.

- **A slow deploy upload looked like a server that was down.** `hop3 deploy` sends the source tree in one request, and the bound meant for the connection handshake was also being applied to the body, so an upload needing more than thirty seconds was killed mid-send and reported as "Could not connect to the Hop3 server. Is it running?" against a server that was answering fine. A 20 MB deploy on a 2 Mbit/s uplink could never succeed. The body now gets its own allowance, a failure reports the error it actually had, and an upload large enough to take a while shows a progress bar instead of going quiet.

- **An expired token surfaced as "Unexpected response format".** An unauthenticated call was answered with a redirect to a login page, which the client followed, so a page of HTML arrived where a JSON-RPC response was expected and the parse error stood in for the real answer. The client no longer follows redirects from the RPC endpoint, which also stops a token being replayed to wherever the redirect points, and an unclassified response now carries its status code and a body excerpt. Relatedly, an admin call denied because of a database error left nothing in the log to say so; the decision to deny is unchanged, but the reason is now recorded.

- **Installing a server from a git checkout failed on a missing `hop3-fetch`.** The installer treated the helper's absence as an error rather than as an older layout that simply does not ship it. It is now skipped with a note when it is not there, and only a helper that exists and cannot be linked stops the install.

## [0.7.1] - 2026/08/02

### Security

Affects every release up to and including 0.7.0. If your hop3-server is reachable from an untrusted network, upgrade. Nothing to reconfigure and no credential to rotate, but weak account passwords should be changed: until now they could be guessed far faster than intended.

- **Password guessing over JSON-RPC was not rate limited.** The web login form has been capped at 5 attempts per IP per minute since 0.5, but `hop3 auth get-token` checks the same credentials and applied no limit, so an attacker could guess ~100x faster by choosing that path. Both now draw on one shared budget.
- **Login failures revealed which accounts exist.** A disabled account answered differently from a wrong password, and an unknown username answered faster than a real one. All three failures now return one identical response in the same time.
- **Signing in over plain HTTP looped instead of failing.** The session cookie is `Secure`, so a browser with no TLS discarded it and the login bounced back to the login page forever, with no error anywhere. It now refuses up front and says why. Local development over HTTP still works with `HOP3_DEBUG=true`.
- **Signing out was a link, so another site could sign you out.** `GET /auth/logout` is now a form POST. Minor by itself, but it was the only state-changing GET, and "every mutation is a POST" is what lets Hop3 ship without CSRF tokens.

Details, and the remaining open items, in `notes/security/`.

One behaviour that looks like a bug and is not: a magic link is spent the moment it is presented, even if the sign-in then fails because the account was deleted or disabled. A link that has been used cannot be replayed, whatever happened next. The one case where the link is *not* spent is a redemption that could never have worked for a reason you can fix (over plain HTTP, above, Hop3 refuses before touching the token), so the link still works once you reach the server over HTTPS.

### Fixed

- **Bugsink's Nix recipe runs its background worker.** The hand-written recipe deployed the web process alone, so the app signed in and then failed on any path that queues work: its "snappea" queue lives in a second database that was never migrated. Configuration and both migrations now run before any worker starts, and the queue worker is declared alongside the web one. The other two Bugsink variants were unaffected.

## [0.7.0] - 2026/07/31

### Changed

- **Consistent command-line names**: the developer deploy tool is now `hop3-deploy-server` (renamed from `hop3-deploy`), part of a pass to give every Hop3 tool one consistent set of flags and verbs.
- **Failed deploys show the real cause**: `hop3 deploy` now surfaces the actual error line once, with a working pointer to the full log (`hop3 app logs --app <app> --build`).

### Added

- **Content-aware health checks**: set `[healthcheck].contains = "..."` and a deploy is only reported healthy when your app actually serves its own page; a bare `200` can be a placeholder or an error page.
- **Server-level email transport** *(experimental)*: set your SMTP submission credentials once with `hop3 server email set … --from-domain example.com`, and per-app email addons created without their own `--smtp-*` inherit them, with no credentials repeated per app. An app can still override with its own provider, and rotating the server transport propagates to every inheriting app.
- **Unified email backend selection** *(experimental)*: `hop3 server email backend <relay|catch|direct>` names the backend every declaring app inherits: `relay` (a provider or corporate smarthost, also spelled `server email set`), `catch` (a dev sink that captures mail and never sends it), and `direct` (below).
- **Direct / self-hosted email backend** *(experimental)*: `hop3 server email backend direct --from-domain example.com` turns the box into its own MTA: Postfix delivers to recipients' MX and opendkim signs outbound mail, with no third party. Hop3 generates the DKIM keypair and prints the exact SPF/DKIM/DMARC records to publish (plus the PTR reminder), runs an SPF/DKIM/DMARC pre-flight, and probes outbound port 25, never claiming "ready" over unpublished DNS or a blocked egress. Needs `--with email` (Postfix + opendkim).
- **Loopback email relay** *(experimental)*: selecting the relay backend now configures a queuing Postfix null-client on `127.0.0.1:25` (via hop3-rootd), and an app that attaches an inheriting email addon is injected `SMTP_HOST=127.0.0.1`; it sends over SMTP to the local relay, which forwards to the provider, so the provider credential never enters an app's environment and the backend is swappable without re-touching apps. Install Postfix with `hop3-install server --with email` (included in `--with all`).
- **Email provider profiles + DKIM auto-verify** *(experimental)*: `hop3 server email set --provider <name>` fills the SMTP host/port for a known provider (`--list-providers`: Resend, Postmark, Brevo, Mailgun/Mailgun-EU, Scaleway TEM (EU-hosted ones flagged). The deliverability pre-flight now also **verifies DKIM** once its selector is known (`--dkim-selector`, or automatically for Resend), instead of only SPF/DMARC.
- **Operator email alerts** *(experimental)*: `hop3 server email notifications on` opts in to being emailed (via the active email backend) when things break: TLS certificate-renewal failures (a cert that stops renewing reaches you before it expires) and **failed deploys** (best-effort, never masking the failure itself). `status` reports whether the channel is actually deliverable, and `test` sends a test message.
- **Safe app upgrades with automatic rollback**: `hop3 app upgrade --app <app>` snapshots the app, redeploys it (rebuilding and running its migrations), verifies it comes back healthy, and if the build, a migration or the health check fails automatically restores the pre-upgrade snapshot instead of leaving you on a half-upgraded app. `hop3 app rollback --app <app>` restores a backup on demand (the most recent by default, `--to <backup-id>` for a specific one).
- **Install apps from the catalog, from the dashboard or the CLI**: 0.6 could browse the signed catalog; 0.7 installs and deploys from it. Twenty apps ship in the official catalog: BookStack, Bugsink, Dolibarr, Easy!Appointments, Forgejo, Gitea, Invoice Ninja, Isso, Kanboard, Keycloak, LimeSurvey, Matomo, Mattermost, Miniflux, Nextcloud, Paheko, Radicale, Uptime Kuma, Vikunja and WordPress, each with an admin account created for you at install time.
- **Every app is verified by signing in, not by returning a page**: each catalog app ships a smoke test that logs in through the app's own authentication with the credential Hop3 generated, and confirms a wrong password is refused. It runs at the end of every deploy (dashboard included), and on demand with `hop3 app check --app <app>`. A `200` from an app that nobody can log into no longer counts as working.
- **`[probe]`, a Hop3-owned account for verification**: an app can declare a non-privileged account whose password Hop3 owns and rotates, so its smoke test keeps working after you change the admin password. Apps that shouldn't have one can leave it out.
- **`hop3 scaffold`**: writes a starter `hop3.toml` for the project in the current directory, with a `#:schema` line so your editor completes and validates the file as you type.
- **Published `hop3.toml` JSON Schema**: at `https://hop3.cloud/schema/hop3.toml.json`, generated from the server's own validation models, so an editor with a TOML language server flags a typo as you type instead of at deploy time.
- **Every bundled app is verified under Nix too.** The two Nix build strategies are now held to the same sign-in bar as the native one: 16 of 16 hand-written recipes and 18 of 19 template-generated ones sign in and refuse a wrong password on a recorded run. Easy!Appointments is the exception: it builds its login form in JavaScript, which neither check can drive.
- **`hop3-deploy-server --provider hetzner --image <image>`**: rebuilds the target server from scratch before deploying, matching `hop3-test`. One command for a genuinely pristine box.

### Fixed

- **A failed server upgrade can no longer report success**: after installing the new code and migrating, the deployer now confirms hop3-server actually came back up before reporting the upgrade complete. If it didn't, the deploy fails loudly with the exact command to revert to the previous release, and a reminder that a forward-migrated schema may also need a pre-upgrade database backup, instead of leaving a silently dead server behind a "complete" message. The restart also picks the right mechanism for the target (systemd or supervisor), so it can't silently keep serving old code.
- **Admin-domain and TLS setup fail loud on a broken nginx reload**: configuring the server's admin domain or its certificate during a deploy now stops with a clear error when nginx can't be reloaded, instead of warning and carrying on, so a "complete" deploy never hides a domain that nginx never actually picked up.
- **Nix apps survive garbage collection**: a running Nix app no longer loses its files to a `nix` garbage-collect. New installs pin auto-GC off and rebuilds keep the previous version rooted, and if anything is ever missing the deploy fails fast with a clear message instead of a slow timeout. Apps that need a newer package set can pin their own nixpkgs revision.
- **`hop3 app restart` checks the Nix closure too**: the check above ran on deploy and start but not on restart, because a restart relaunches the worker from its existing config without going through the start path. A restart against a reclaimed closure therefore came up and died into a health-check timeout with nothing pointing at the cause. It now aborts with the same message naming the missing store path.
- **A fresh install no longer serves a stale configuration**: the installer now restarts hop3-server once its configuration file is written, so a first-time install picks up its operator email, database credentials and admin domain immediately. Previously, on a brand-new server the service started *before* that file existed and cached the empty values, so every app using the built-in admin account failed to deploy with "this server has no operator email", even though the setting was correct on disk. Redeploys were unaffected, which is what made it a fresh-install-only bug.
- **Build failures inside your Dockerfile are reported right away, not retried as phantom registry errors**: a step that fails in your own build (for example a truncated download surfacing as "tar: Error is not recoverable") is now surfaced immediately instead of being mistaken for a transient container-registry outage and retried three times. Genuine registry blips are still retried.
- **Apps are served over HTTPS by default**: plain HTTP now redirects. Apps that set `Secure` cookies (most of them) were unloggable over the HTTP vhost, because the browser correctly refused to send the session cookie back, and the login silently looped.
- **PHP's built-in server gets more than one worker**: it is single-threaded, so any app that makes a request to itself while installing, as Nextcloud's installer does, deadlocked against its own only worker and never finished.
- **A failed install can be retried**: installing an app from the catalog recorded it before deploying, so if the deploy failed, every retry was refused with "already exists", leaving an app you could neither use nor reinstall. A second install now resumes one whose deploy never completed.
- **`[build].build` runs in every language**: the setting was read and then ignored by seven of the twelve toolchains, so a project's declared build command silently never ran.
- **`--clean` reclaims addon databases**: a clean reinstall wiped Hop3's records but left the databases behind, so the next install found a populated database and adopted it. It now stops the apps, drops what it tracks, and sweeps databases it has lost track of. MySQL also refuses to adopt a populated database it holds no credentials for, instead of silently taking it over.
- **`hop3 app credentials` no longer shows a password for an account that was never created**: when an app's own bootstrap failed, the generated credential was still presented as if it worked. The failure is now named, and a bootstrap error includes the failing command's output instead of only an exit status.
- **`--app` works on `app check`, `app upgrade` and `app rollback`**: the three commands documented the flag and then rejected it.
- **Addon teardown reports what it could not remove** instead of leaving storage behind.
- **More bundled apps deploy and verify correctly**, from packaging and content-check fixes across several apps.
- **Authentication hardening**: remediated the findings from the June 2026 auth audit.
- **DNS**: fixed some server-side DNS resolution issues.

### Security

These are defects in Hop3's own bundled application recipes, all found by the sign-in check described above and none visible to a deploy that returned HTTP 200. Anyone who deployed the affected Nix variants should redeploy.

- **Radicale served without authentication.** The Nix recipes set the calendar server's auth type from a variable that defaulted to `none` and was never set, so every calendar and address book was readable by anyone who asked. Authentication is now declared in the recipe where no environment can switch it off, and the config is rewritten on every start so a deployment that once ran open does not stay open.
- **Isso's moderation dashboard was served disabled.** Its config carried no administrator section, so `/admin/` never asked for a password. It is now enabled against the generated credential, comment moderation is on, and the app refuses to start without the credential rather than serving the dashboard open.
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
- **Admin-domain TLS fixed on rootd hosts**: `acme.sh` reloaded nginx as the `hop3` user (blocked by rootd). The deploy now reloads nginx itself and checks for the cert on disk instead of trusting acme.sh's exit code.
- **Self-signed cert upgraded to Let's Encrypt**: a previously-issued self-signed certificate is now replaced when `--acme-email` is added. When self-signed, the deploy tells you why.
- **Server knows its own admin domain**: `hop3-deploy` records `ADMIN_DOMAIN` so magic links and `addon expose` URLs use the right hostname.
- **Dashboard login survives redeploys**: web auth now uses a signed JWT cookie instead of a server-side session, matching the CLI credential. Stays valid across restarts.
- **`HOP3_UNSAFE` production override now works**: the auth guards re-read the env instead of caching an import-time snapshot.
- **Unknown CLI flags fail loud**: the RPC argument parser rejects unrecognized tokens with an error instead of silently dropping them. This also fixed `hop3 backup list --app X` ignoring the filter.
- **`hop3 context use` recognizes global contexts**: instead of "not found", it now points to the right mechanism (`hop3 login --context` or `--context` per command).

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

- **`--context` resolution fails loud**: the CLI shows the full resolution chain instead of silently falling back.
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
- **Server vs context vocabulary (BREAKING, ADR 042)**: the old global "context" is now a *server*, and "context" means a project deploy target; existing config is migrated on first run.
- **Testing layers (ADR 043)**: the test suite is three layers selected by speed tier; a plain `pytest` run never starts Docker.
- **More reliable deploys**: clearer messages about already-set env vars, IPv4 addon hosts to avoid IPv6 resolution issues, and assorted build and worker-precedence fixes.
- **Safer upgrades**: pending database migrations run on upgrade, and an existing virtualenv is no longer replaced.
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

Initial release: core architecture, app builders, addon support, SQLAlchemy models, and the first test runner.

[Unreleased]: https://github.com/abilian/hop3/compare/0.7.1...HEAD
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
