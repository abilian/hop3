# Signing In

Hop3 has two surfaces, and they hold two different credentials.

| | What it is | Where it lives | How long it lasts |
|---|---|---|---|
| **CLI** (`hop3`) | A bearer token (JWT) | `~/.config/hop3-cli/credentials.toml`, on your machine | 24 hours (`HOP3_TOKEN_EXPIRY_HOURS`) |
| **Web dashboard** | A browser session cookie | Your browser | 14 days |

Signing into one does not sign you into the other. But one thing opens both: **SSH access to the server**. If you can `ssh` to the box, you are already an administrator of the Hop3 running on it — that is the design ([ADR 014](https://github.com/abilian/hop3/blob/main/notes/adrs/014-authentication-bootstrap.md)), and it is why you almost never need the admin password.

## Signing the CLI in

Run this on your own machine, not on the server:

```bash
hop3 login --ssh root@your-server.com
```

It asks the server for an API token over SSH and stores it, creating an admin account if there isn't one. No password. From then on `hop3 apps`, `hop3 deploy` and the rest work against that server. (`hop3 auth login` is the same command — `hop3 login` is its alias.)

## Getting into the dashboard

```bash
hop3 login --web root@your-server.com
```

Despite the flag names, this is not the alternative to `--ssh`. It travels over SSH too, and it is not a login: it prints a one-time URL for you to open in a browser, which expires after 5 minutes and works once. Opening it is what creates the browser session.

You need it *in addition to* `--ssh`, not instead of it — the two surfaces hold separate credentials, and neither grants the other.

## What about the admin password?

`hop3-deploy-server` generates one when it creates the admin account, and does not print it unless you pass `--verbose`. That is deliberate: it is not the way in, and a secret half-shown in terminal scrollback is a secret leaked.

You need it in exactly one case — signing into the dashboard's own form from a machine with no SSH access to the server. To set one you know:

```bash
hop3 login --ssh root@your-server.com
hop3 user set-password admin --stdin      # reads the new password from stdin
```

If you cannot run `hop3` at all, do it on the server. Run `hop3-server` as the `hop3` user, so the database stays owned by `hop3` and not by `root`:

```bash
ssh root@your-server.com
sudo -u hop3 /home/hop3/venv/bin/hop3-server admin:reset-password admin
```

## The dashboard needs HTTPS

The session cookie is marked `Secure`, so a browser on plain `http://` accepts it and then never sends it back: the login would redirect to the dashboard, find no credential, and bounce back to the login page forever. Hop3 refuses that instead of looping, and says so on the login page.

So give the server a domain — `hop3-deploy-server --host hop3.example.com`, or `--admin-domain` for a separate one — and the dashboard works at `https://<that domain>/`. For local development, `HOP3_DEBUG=true` drops the `Secure` flag and plain HTTP works.

The CLI has no such constraint: `hop3 login --ssh` works against a bare IP address.

## Naming your servers

By default the CLI talks to whichever server you signed into last. Name them instead, and a flag picks one:

```bash
hop3 login --context dev  --ssh root@dev.example.com
hop3 login --context prod --ssh root@prod.example.com

hop3 apps --context dev      # ask dev
hop3 apps                    # ask the last one you named — here, prod
```

`--context <name>` records the server under that name and makes it the default target, so you only pass the flag when you want the *other* one. Run `hop3 context --help` for the full precedence rules and the project-scoped form, where a context also carries the app, its domains and its environment.

## Checking and clearing

```bash
hop3 auth whoami     # which user, on which server
hop3 logout          # revoke this machine's token, then clear it
```

## Adding people

```bash
hop3 user add alice alice@example.com --stdin   # password from stdin
hop3 user grant-admin alice
hop3 user list
```

Every Hop3 account is operator-equivalent today: there is no per-app ownership and no MFA. Read [Security](../guides/security.md) before you hand one out.

## When something is wrong

| Symptom | Cause | Fix |
|---|---|---|
| `hop3` says you are not authenticated | The token expired (24 h) | `hop3 login --ssh root@your-server.com` |
| The dashboard login bounces back to itself | Plain HTTP, `Secure` cookie dropped | Give the server a domain and a certificate |
| The magic link says it is invalid | Used already, or older than 5 minutes | Generate another with `hop3 login --web` |
| `hop3 apps` answers about the wrong server | It went to the default target | `hop3 apps --context <name>`, or sign in again with `--context` |
| You have the password but not SSH | Nothing is broken | `hop3 login` prompts for username and password |
