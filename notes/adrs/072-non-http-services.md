# ADR 072: Non-HTTP Services: Ports, Shared SSH, Media Relays and Mail

- **Status**: Proposed
- **Type**: Architecture
- **Created**: 2026-11-09
- **Extends**: [ADR 045](./045-fixed-port-registry.md) (the fixed-port registry)
- **Related-ADRs**: [041](./041-privileged-operations-agent.md) (rootd, which this ADR gives new operations), [048](./048-server-config-and-secret-storage.md) (where the TURN secret is kept), [054](./054-email-transport-and-notifications.md) (email as a backing service), [055](./055-app-runtime-uid-separation.md) (per-app users, which the shared SSH entry point requires), [068](./068-guest-networking.md) (platform networking for micro-VM guests)

## Context

Hop3 multiplexes one protocol. nginx virtual-hosts HTTP by `Host:`, so any number of apps share ports 80 and 443. Other protocols each reach the host on a dedicated port, with no proxy in front. ADR 045 made those ports a managed resource: an app declares them in `[[ports]]`, a second claim on the same port is refused before the build, and rootd opens the firewall on a successful deploy. The catalog's owncast (RTMP, `1935/tcp`) and Matrix Synapse (federation, `8448/tcp`) rely on it.

Three classes of application still cannot be packaged. Each one exposes a gap in the platform.

**Forges** (Gitea, Forgejo, GitLab, Pagure) accept pushes over SSH. Port 22 belongs to the host's sshd, and ADR 045 rejects it in `[[ports]]`. A forge left to manage SSH itself rewrites the running user's `~/.ssh/authorized_keys`, which on Hop3 holds the forced-command key behind `git push` and `hop3 app shell`. The catalog's Gitea and Forgejo recipes therefore set `DISABLE_SSH = true`: they serve Git over HTTPS only.

**Real-time media** (Galene, Jitsi Meet, Nextcloud Talk, Matrix calls) sends audio and video over UDP. A client behind a restrictive NAT or firewall reaches the media server only through a TURN relay, which listens on 3478 (UDP and TCP) and 5349 (TLS) and relays through a range of UDP ports. A media server may also need a dedicated UDP port (Jitsi's videobridge uses `10000/udp`). ADR 045 declares single ports only.

**Mail hosting** needs ports 25, 465, 587 and 993, all below 1024. App processes run unprivileged and cannot bind them (`PLATFORM-BLOCKERS` #25 records Stalwart and all mail servers as blocked on this). A mail server also needs a certificate for its hostname. Finally, it must share the host with the platform's MTA: ADR 054's queuing relay listens on loopback port 25.

ADR 045 also leaves four gaps that affect all non-HTTP apps:

- When rootd is unreachable, the deploy succeeds with a warning and leaves the firewall closed, so the port cannot be reached from outside the host. `hop3 addon expose` (the sibling path) and ADR 068's guest rules already treat the rule as mandatory.
- The readiness check probes HTTP only, so a crashed RTMP or SMTP listener reads as a running app.
- A Docker app's declared ports are claimed but not published.
- Nothing hands a certificate to a protocol other than HTTP: certificates are installed for nginx alone.

## Goals

1. Each declared port is part of the deploy's contract: opened, reachable and probed, or the deploy fails with a diagnosis.
2. An app can serve a port below 1024 without running privileged code and without the right to bind ports it did not declare.
3. Several forges share port 22 with the host's sshd and with Hop3's key, each under a distinct login name.
4. Media apps get a TURN relay without each app running one.
5. One server can host a complete mail system, with Hop3's checks covering what makes mail deliverable.
6. Each mechanism is general. No app gets a dedicated code path.

## Decision

### 1. Declared ports are mandatory

A deploy fails when its firewall rule cannot be applied, whether rootd rejected the rule or could not be reached. The claim rolls back with the deploy session, as it does for any other failure. `open_fixed_ports` then behaves as addon exposure and ADR 068 already do.

Before an app is recorded as RUNNING, each declared TCP port must accept a connection, within the same start timeout as the HTTP check. A UDP port cannot be probed without speaking the protocol, so a declared UDP port is not probed; the app's health check covers it.

### 2. Ports below 1024: a redirect owned by rootd

An app declaring a port below 1024 never binds it. Hop3 allocates an unprivileged internal port, records it on the claim, and passes it to the app as `HOP3_PORT_<NAME>`. A low port therefore requires a `name`. The internal port stays stable across redeploys, as the addon-exposure port does. rootd adds a `redirect` rule in a `nat` `prerouting` chain of the `inet hop3` table, from the public port to the internal one. The redirect keeps the client's source address, which SMTP's anti-abuse checks depend on. It applies to traffic arriving from the network; a local client connects to the internal port.

A port of 1024 or above keeps ADR 045's behaviour: the app binds the declared number itself, since many apps hardcode theirs (owncast's 1935).

The redirect is one more rule in the table rootd already owns, applied, recorded and reconciled like the firewall rules. The operations (`firewall.add_redirect`, `firewall.remove_redirect`) join ADR 041 as a new section that states their threat model; the main property is that rootd redirects only to ports above 1024 and only for a port held by a claim.

**Alternatives, undecided:**

- **`CAP_NET_BIND_SERVICE` on the app's processes.** Under ADR 055 the vassal's `setpriv` drop could keep this one capability as ambient.
  - *Buys:* no address translation; the app binds the real port, and local and remote clients see the same number.
  - *Costs:* the capability covers all ports below 1024, declared or not, so the registry no longer bounds what an app can bind. An app could take 53 or 123, or 443 during an nginx restart. It also depends on ADR 055's drop, and does nothing for Docker. Setting it on the binary instead (`setcap`) adds two costs: an interpreter given the capability passes it to each script it runs, and a rebuild replaces the file and loses it.
- **A `systemd-socket-proxyd` forwarder** (rootd's `proxy.add`, which addon exposure already uses).
  - *Buys:* it exists and is tested.
  - *Costs:* TCP only, so no UDP; one process per port; and the app sees all connections as coming from 127.0.0.1, which defeats SMTP's checks on the sender's address.
- **Lowering `net.ipv4.ip_unprivileged_port_start`.**
  - *Buys:* nothing to build.
  - *Costs:* it applies to all users on the host.

**What decides:** whether the registry has to bound what an app can bind (the capability fails that test) and whether the app has to see the client's address (the forwarder fails that one).

### 3. Port ranges

A `[[ports]]` entry may give a range: `number` is the first port and `last` the final one, capped at 16384 ports and only above 1024. A claim records both bounds. Conflict detection becomes an overlap test, and since a unique constraint cannot express overlap, the test and the insert run in one serialized write (SQLite serializes writers; on PostgreSQL the claim table is locked for the check). rootd writes one rule per range.

### 4. Docker apps publish their declared ports

The generated compose file publishes each declared port to the host, low ports included, since Docker's proxy binds them. The claim and the firewall rule are the same as for a native app, and readiness probes the published port. The redirect of §2 is not used for Docker.

### 5. Certificates for non-HTTP protocols

An app may ask for a copy of its certificate with `[tls] export = true`. Hop3 then installs the certificate and key for the app's hostnames into `apps/<app>/tls/` (`fullchain.pem`, `privkey.pem`, readable by the app's user only), passes their paths as `HOP3_TLS_CERT` and `HOP3_TLS_KEY`, and restarts the app when the certificate is renewed. The hostname is one of the app's `[domains]`, so the engine that already serves nginx issues, validates and renews it. A renewal that cannot install the files fails the same way an nginx installation failure does, and is reported through the certificate health checks.

### 6. Port 22 shared by login name

sshd already tells users apart by login name, as nginx tells apps apart by `Host:`. A forge declares the name it accepts pushes under and the command that answers sshd's key lookups:

```toml
[ssh]
user = "git"
keys-command = "gitea keys -e git -u %u -t %t -k %k"
```

The login name is a host-wide resource, claimed in a registry beside the port claims, unique, refused before the build if taken, and never one of the names the system or Hop3 uses (`root`, `hop3`, any existing account). On a successful deploy, rootd takes four steps:

1. creates the login account as an alias of the app's user (same uid and gid, `useradd -o`), with the app's home and no password;
2. writes `/etc/ssh/sshd_config.d/hop3-<app>.conf` with a `Match User <name>` block: `AuthorizedKeysFile none`, `AuthorizedKeysCommand` set to a root-owned helper, `AuthorizedKeysCommandUser` set to the app's user, no password or keyboard-interactive authentication, `DisableForwarding yes`, `PermitTTY no`;
3. validates the result with `sshd -t`, and checks with `sshd -T -C user=<name>,…` that the login resolves to the new block while `root` and `hop3` resolve exactly as before;
4. reloads sshd, never restarts it.

Any failure removes the file and the account, and fails the deploy. Teardown removes both and reloads.

sshd requires the keys command to be root-owned and unwritable by others, and the forge's binary lives in the app's tree. The helper (`/usr/libexec/hop3/ssh-keys <app>`) fills that gap: it runs as the app's user, loads the app's environment, and executes the declared `keys-command`. The forge answers with `authorized_keys` lines that set a `command=` restriction of its choosing (`gitea serv key-<id>`), so the forge alone decides which keys are accepted and what a push runs. The forge writes no key file, which removes the hazard behind the catalog recipes' `DISABLE_SSH`, and Hop3's keys play no part in the forge's login.

The app's environment receives `HOP3_SSH_USER` and `HOP3_SSH_HOST`, so the clone URLs the forge displays (`git@host:owner/repo.git`) are right without per-recipe configuration.

**Authority.** A key the forge accepts runs under the app's user. A compromised forge could hand out a shell, but only with the authority the forge's process already has. This holds only once each app has a dedicated user: before ADR 055 the alias would share the uid of `hop3`, which can read `hop3.db`. This section therefore requires ADR 055: Hop3 refuses `[ssh]` on an app that runs as `hop3`.

Gitea and Forgejo support this mode as documented (`keys`, with `START_SSH_SERVER = false`, `SSH_CREATE_AUTHORIZED_KEYS_FILE = false`). GitLab does through `gitlab-shell-authorized-keys-check`. Other forges are checked when packaged.

**Alternatives for the login account, undecided:**

- **An alias of the app's uid (as above).**
  - *Buys:* a short, conventional name (`git@`); the forge's processes run as the forge.
  - *Costs:* two names for one uid, which tools listing users will show; teardown removes the alias first.
- **The app's user (`hop3-app-gitea@host`).**
  - *Buys:* no alias.
  - *Costs:* the name appears in each clone URL.
- **A separate user in the app's group.**
  - *Buys:* a distinct uid in audit logs.
  - *Costs:* the forge's repositories must be group-writable. Forges assume the push runs as the user that owns them.

**What decides:** whether a second name for a uid is acceptable on the hosts Hop3 supports.

A forge that brings an SSH server (Gitea's `START_SSH_SERVER`) can instead declare a port above 1024 in `[[ports]]`. That works under ADR 045 with no new mechanism, at the cost of a port in each clone URL (`ssh://git@host:2222/…`).

### 7. TURN as a platform service

TURN serves any number of apps through one shared secret, so it is a platform service with an addon in front, like the email relay. The installer provides coturn (`--with turn`), configured with:

- `use-auth-secret`, with the secret root-owned and kept out of the addon namespace (ADR 048);
- 3478 over UDP and TCP, and 5349 over TLS with the server's certificate;
- a relay range;
- `no-multicast-peers`, and `denied-peer-ip` for loopback and the private ranges, so the relay cannot be used to reach the host's services or its neighbours.

The service's ports are claimed in the registry as platform claims, so an app declaring 3478 is refused with a message naming the TURN service.

`hop3 addon attach <name> --app <app> --type turn` injects `TURN_URIS`, `TURN_SECRET` and `TURN_REALM`. Apps derive short-lived credentials from the secret, in the scheme coturn calls the TURN REST API: Synapse's `turn_shared_secret`, Galene's `hmac-sha1` ICE servers, Jitsi and Nextcloud Talk. An app's media ports (Jitsi's `10000/udp`, a media server's range) remain in the app's `[[ports]]`.

### 8. A mail host is an app that becomes the email backend

One server hosts at most one mail system: SMTP on port 25 cannot be shared among receivers on one address. The mail server is an app, packaged like any other. It declares 25, 465, 587 and 993 (§2), exports its certificate (§5), and serves a web administration over HTTP.

ADR 054 gains a backend kind, **local mail host**, which names that app. With it selected:

- the platform's loopback relay delivers to the mail host's submission port, so apps keep the endpoint and variables they already use;
- the mail host delivers outbound mail and signs it with its DKIM key;
- inbound mail arrives on port 25 through the redirect, which leaves loopback port 25 to the relay.

The backend reports ready only when the checks pass:

- MX for each mail domain names the host;
- the reverse DNS of the public address matches the name the host announces;
- outbound connections to port 25 succeed (a connection to a well-known MX, with no mail sent);
- SPF, DKIM and DMARC are published (ADR 054's checks).

The first two depend on the DNS and hosting provider, so the diagnosis names who has to act. As in ADR 054, the mail host may be deployed before the DNS is published; it cannot be made the active backend until the checks pass.

Stalwart is the first recipe: one binary for SMTP, IMAP and JMAP, with built-in DKIM signing and spam filtering. The mechanism names no server.

### 9. Out of scope

- **Two apps on the same public port.** That needs one address per app. With IPv6 an address costs nothing, but the model belongs with ADR 068's networking, not here.
- **Routing several TLS services on one port by SNI** (an nginx `stream` block with `ssl_preread`). It would let two implicit-TLS services (IMAPS, SMTPS) share a port, but not STARTTLS protocols such as SMTP on 25. No packaged app needs it.
- **BigBlueButton.** It expects a specific Ubuntu release, its own nginx and a large share of the UDP port space, which amounts to a dedicated machine.

## Acceptance

Each mechanism is accepted by a fixture that exercises it on Docker and on a systemd server, then by a catalog app:

- **Mandatory ports:** a deploy with rootd stopped fails and leaves no claim; an app with a listener that exits during the start is not RUNNING.
- **Low ports:** a TCP fixture declaring port 25 answers on 25 from outside the host and sees the client's real address; destroy removes the claim, the rule and the listener.
- **Ranges:** a UDP fixture declaring a range is reachable on its first and last ports; an overlapping claim is refused, naming the holder.
- **Shared SSH:** Gitea, native, accepts a clone and a push at `git@host` on port 22 while `git push` to Hop3 and `hop3 app shell` keep working with Hop3's key; destroy removes the drop-in and the account and leaves `sshd -T` output as it was before the deploy.
- **TURN:** an allocation with credentials derived from the attached secret succeeds; an allocation towards 127.0.0.1 or a private address is refused.
- **Mail host:** Stalwart receives a message sent to port 25 from another container, an app attached to the email addon sends through it, and the backend refuses to become active while a check fails.

## Consequences

### Positive

- Forges, media apps and mail servers become packageable without per-app workarounds. Forges serve Git over SSH again.
- Each non-HTTP port is held to the same contract as HTTP: claimed, opened, probed and removed, with a diagnosis at each step.
- Hop3's keys stay out of a forge's reach, and the hazard behind the catalog's `DISABLE_SSH` disappears.
- The email addon gains a sovereign backend that goes live only once its deliverability checks pass.

### Negative

- rootd edits sshd's configuration. A broken file would lock operators out, hence the validation, the before-and-after comparison and the reload-only rule; the risk remains the most serious in this ADR.
- Address translation adds a layer to diagnose: an app that answers on the internal port and not on the public one has a rule problem, which the diagnosis has to name.
- The TURN secret is shared by all attached apps, so any of them can mint relay credentials.
- A mail host makes one app a dependency of all apps that send mail. Destroying it requires moving the email backend elsewhere first; the destroy refuses until then.

## Open questions

1. **Per-app TURN secrets.** coturn accepts several secrets; one per attached app would let a single app's access be revoked. Whether that is worth the reconfiguration on each attach is open.
2. **The alias account and ADR 055's teardown.** Teardown removes everything the uid could have written (ADR 055 §7). The alias shares the uid, so it is removed first, but `userdel` of an alias for a uid still in use needs testing on each supported distribution.
3. **IPv6.** rootd's `source` restriction is IPv4 only. The redirect and the ranges should be written for both families from the start; whether `source` follows in the same change is open.
4. **Certificate scope.** A mail host often serves `mail.example.org` while its addresses are at `example.org`. Whether `[tls] export` covers all hosts in `[domains]` or a declared subset is open.
