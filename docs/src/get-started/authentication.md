# Signing In

Hop3 has two surfaces, and each holds a different credential.

| | What it is | Where it lives | How long it lasts |
|---|---|---|---|
| **CLI** (`hop3`) | A bearer token (JWT) | `~/.config/hop3-cli/credentials.toml`, on your machine | 24 hours (`HOP3_TOKEN_EXPIRY_HOURS`) |
| **Web dashboard** | A browser session cookie | Your browser | 14 days |

Signing into one does not sign you into the other. But one thing opens both: **SSH access to the server**. If you can `ssh` to the server, you are already an administrator of the Hop3 running on it. That is the design ([ADR 014](https://github.com/abilian/hop3/blob/main/notes/adrs/014-authentication-bootstrap.md)), which is why you almost never need the admin password.

## Signing the CLI in

Run this on your own machine, not on the server:

```bash
hop3 login root@your-server.com
```

It asks the server for an API token over SSH and stores it, creating an admin account if there isn't one. No password. It prints what it recorded:

```
Signed in to https://your-server.com as admin  (context 'default')
```

From then on `hop3 apps`, `hop3 deploy` and the rest work against that server.

A bare hostname means `root@`: the line above shows the address it resolved to, so you can see the substitution.

## SSH gets you in; HTTPS carries the everyday traffic

The two are different jobs. The address above is the giveaway: you signed in over SSH, but the recorded target is `https://`.

| Role | When it is used |
|---|---|
| **Everyday**: `https://<your domain>` | every command |
| **Bootstrap**: `ssh://root@host` | minting a token, including renewing an expired one, unattended |
| **Rescue**: `hop3 apps --via-ssh` | when the everyday route breaks |

Only the server knows how it is fronted, so the login asks it. If the answer is a domain your machine can verify, that becomes the everyday address and routine work stops going through a root shell.

If it can't, the login says so and keeps the tunnel:

```
  note: every command will tunnel over SSH as root, because it has no admin
        domain, so there is no HTTPS endpoint.
        Give it one to serve the API and the dashboard over HTTPS:
        hop3-deploy-server --host your-server.com --admin-domain <fqdn>
```

The same three causes apply: no admin domain, a certificate your machine doesn't trust, or a server too old to answer. Each is named.

## Getting into the dashboard

```bash
hop3 login --browser
```

It travels over SSH too, but it is not a login: it prints a one-time URL for you to open in a browser, good for 5 minutes and one use. Opening the link creates the browser session.

You need it *in addition to* signing the CLI in; the two surfaces hold separate credentials, and neither grants the other.

Bare `--browser` asks the server you are already signed into. Name one when you aren't yet:

```bash
hop3 login --browser root@your-server.com
```

## The dashboard needs HTTPS

The session cookie is marked `Secure`, so a browser on plain `http://` accepts it and then never sends it back: the login would redirect to the dashboard, find no credential, and bounce back to the login page forever. Hop3 breaks the loop and says so on the login page.

So give the server a domain (`hop3-deploy-server --host hop3.example.com`, or `--admin-domain` for a separate one) and the dashboard works at `https://<that domain>/`. For local development, `HOP3_DEBUG=true` drops the `Secure` flag and plain HTTP works.

This is the same missing piece that keeps the CLI on the SSH tunnel: give the server a domain and both symptoms go away.

## What about the admin password?

`hop3-deploy-server` generates one when it creates the admin account, and does not print it unless you pass `--verbose`. That is deliberate: it is not the way in. A secret half-shown in terminal scrollback is a secret leaked.

You need it in exactly one case: signing into the dashboard's own form from a machine with no SSH access to the server. To set one you know:

```bash
hop3 login root@your-server.com
hop3 user set-password admin --stdin      # reads the new password from stdin
```

If you cannot run `hop3` at all, do it on the server. Run `hop3-server` as the `hop3` user, so the database stays owned by `hop3` and not by `root`:

```bash
ssh root@your-server.com
sudo -u hop3 /home/hop3/venv/bin/hop3-server admin:reset-password admin
```

## Naming your servers

Every target has a name. A login that names none records `default`:

```bash
hop3 login root@dev.example.com                    # context 'default'
hop3 login --context prod root@prod.example.com    # context 'prod'

hop3 apps                    # the current target — here, prod
hop3 apps --context default  # the other one
```

`--context <name>` records the server under that name and makes it current, so you only pass the flag when you want a different one.

A second server logged in *without* a name is refused: "I replaced my server" and "I have two now" look identical from the CLI's side. Guessing wrong sends your next `hop3 destroy` to the wrong machine. Name it, or drop the old one first; the error says both.

`hop3 context` lists what you have. Run `hop3 context --help` for the project-scoped form, where a context also carries the app, its domains and its environment.

### Two names are taken

`default` is the global target a nameless login writes, so a *project* context cannot use it: a committed `[contexts.default]` would shadow it for everyone working in that checkout.

`env` is the target your shell declares. If `HOP3_API_URL` is set, commands go there, ahead of anything stored. It is listed and named like any other context, so the override is visible.

## Checking and clearing

```bash
hop3 auth whoami     # which user, on which server
hop3 logout          # revoke this machine's token, then clear it
```

## Adding people

```bash
hop3 user add alice alice@example.com --stdin --role deployer   # password from stdin
hop3 user set-role alice admin
hop3 user list
```

Every account holds one role: `admin`, `deployer`, `viewer` or `member` (the default). A deployer's builds run with the control plane's own privileges, so treat it as an administrator, and there is no MFA yet. Read [Security](../guides/security.md#the-account-model-four-roles) before you hand one out.

## When something is wrong

| Symptom | Cause | Fix |
|---|---|---|
| `hop3` says there is no credential for a server | The token expired and no SSH route is recorded | `hop3 login root@your-server.com` |
| Every command is slow and opens an SSH connection | No admin domain, so the tunnel is the only route | Give the server a domain, then sign in again |
| HTTPS is down but SSH works | Certificate expired, proxy stopped, DNS wrong | `hop3 apps --via-ssh` for one command |
| The dashboard login bounces back to itself | Plain HTTP, `Secure` cookie dropped | Give the server a domain and a certificate |
| The magic link says it is invalid | Used already, or older than 5 minutes | Generate another with `hop3 login --browser` |
| `hop3 apps` answers about the wrong server | `HOP3_API_URL` is exported, or the current context is not the one you meant | `hop3 context` to see where it goes; `unset HOP3_API_URL`, or pass `--context <name>` |
| You have the password but not SSH | Nothing is broken | `hop3 login` prompts for username and password |

The old spellings still work: `hop3 login --ssh <target>` for the positional form, `--web` for `--browser`, and `hop3 auth login` for `hop3 login`.

