# Security Model

This page is for anyone reading Hop3's code with security in mind: contributors, reviewers, and auditors, human or automated. It describes the trust boundaries the platform is built around, and how to run a review against it.

If you operate a Hop3 server, read [Security](../guides/security.md). To report a vulnerability, see the [Security Policy](../reference/policies/security-policy.md).

!!! note "Where the full catalogue lives"

    This page covers the model and the method. The exhaustive site-by-site catalogue of *reviewed and deliberate* code patterns lives in [`notes/security/security-model.md`](https://github.com/abilian/hop3/blob/main/notes/security/security-model.md) in the repository, alongside the per-round audit reports. Deliberately one copy: a duplicated catalogue drifts, and a drifted catalogue is worse than none.

## Actors

Five actors, with real privilege boundaries between them. Most security findings resolve to a single question: **across which of these boundaries does the tainted data flow?** When the answer is "none", the finding is misaligned with the model however alarming the surface code looks.

| Actor | Trust posture |
|-------|---------------|
| **Operator** | The sysadmin who installed Hop3; root on the host. Fully trusted. Operator compromise is host compromise, and is not modelled. |
| **App deployer** | An authenticated user pushing apps over the CLI or RPC. Trusted inside the application runtime: they choose its entrypoint, env and dependencies. Cannot escalate to operator. |
| **hop3-server** | The ASGI daemon, running as the unprivileged `hop3` user. Confidant of both actors above; not internet-trusted. Everything it exposes on its listening port is public attack surface. |
| **hop3-cli / hop3-tui** | Workstation tools. Trusted by the user invoking them, since that user owns the shell. Their threats are a hostile *remote server*, a malicious `hop3.toml` in a cloned repo, and on-disk permissions of the token file. |
| **hop3-rootd** | A small root daemon on a Unix socket, performing what `hop3-server` cannot. Caller identity is enforced by the kernel (`SO_PEERCRED`); execution is restricted to an allow-list of absolute binary paths. |

## Boundaries

Three boundaries carry the security weight:

1. **Unauthenticated HTTP → authenticated session.** Login, magic-link redemption, JWT validation, rate limiting. Anything reachable before the token check is internet-exposed.
2. **App deployer → host.** A deployer supplies a `hop3.toml` and a tarball; Hop3 turns those into a process supervisor entry, a proxy configuration and an addon-secrets record. Sinks that interpolate deployer-controlled strings into shell, SQL, config files or filesystem paths are where to look.
3. **hop3 user → root.** `hop3-server` asks `hop3-rootd` to perform a privileged operation over a local socket. Every operation revalidates its arguments inside rootd.

There is deliberately **no boundary between two app deployers** (see below).

## The control plane is single-tenant

An authenticated account is an operator-equivalent credential: it can act on any application and any addon on the host. This is by design for the current release.

Structurally, `App` has no owner column, addon credentials bind to an application, and commands do not receive the caller's identity unless they opt in, which only the user-management surface does. The RPC dispatcher authenticates and checks scope; it has nothing to check ownership against.

Consequences when reviewing:

- "User X can reach user Y's application" is **the model**. It belongs against the ownership work.
- "An *unauthenticated* caller reaches an app-scoped command" **is** a vulnerability, and a serious one.
- Leaking one account's credentials to another is still in scope. Operator-equivalence is a statement about authorization, not a licence to leak secrets across the RPC boundary.

Note that single-tenant is not the same claim as single-server. Hop3 targets one server per deployment today and one tenant per deployment today; those are separate properties, and per-application ownership (multi-tenancy on one host) is the planned next step.

## In and out of scope

**In scope:** crossing the unauthenticated boundary; escaping "deploy an app" into "execute as operator" or "modify state outside the application"; leaking tokens, passwords or keys through argv, logs, error messages or world-readable files; replay or fixation of tokens and magic links; denial of service that bricks the server or starves another application; supply-chain integrity of pinned dependencies.

**Out of scope:** post-host-compromise scenarios ("an attacker who is already root could…"); self-injection on a developer's own workstation; key custody beyond the process environment (no HSM/TPM/KMS) and automated key rotation; encryption of the database *file* itself, distinct from the secrets inside it; separation between accounts on the control plane; a control-plane audit log; multi-node isolation; compliance certification; multi-factor authentication.

Several of those are planned work. The repository note tracks which.

## Conventions in the source

Two grep-able comment prefixes:

- **`# SECURITY:`**: this code *is* a security control. Weakening it changes the platform's posture. The comment names the threat and any upstream contract the control depends on.
- **`# AUDIT:`**: this code *looks* suspicious, has been reviewed, and carries the boundary argument that makes it safe. Use it where a reviewer would otherwise re-flag the construction.

```sh
git grep -n -E "^[ \t]*# (SECURITY|AUDIT):" -- packages/
```

Whole-module reasoning goes in a top-of-file *Trust model* docstring instead.

## Sister-site discipline

A hardening pattern that applies in one module almost certainly applies in others. This is the single most reliable source of real findings in Hop3's review history. In one round, *every* confirmed finding was a pattern already fixed elsewhere and missed in a sibling. A password had moved off the command line in one package while its neighbour still passed it there. An atomic write with restricted permissions covered one config file and skipped its twin. A hostname validator sat in one proxy plugin and was missing from two others.

**When you fix a hardening pattern, grep for the anti-pattern across every package before calling the fix done.** Search for the *anti-pattern's shape*, not the fix's. Anything you find belongs in the same change or an immediate follow-up.

## Running a review

### Brief the reviewer first

Give any reviewer (an LLM included) this page and the repository catalogue before it reads a line of source. Measurably fewer invalid findings come back: after the catalogue first existed, reviewing models began classifying constructions as intentional-and-documented, and the recurring noise of earlier rounds largely stopped.

State the local-only threat model explicitly, because it is the most common source of invalid findings. `hop3-installer`, `hop3-cli` and `hop3-tui` run on the user's own machine with that user's privileges on input that user typed. Injection there crosses no boundary. Reviewers not told this reliably produce reports full of "command injection via `--branch`" and "no authentication on the CLI".

### Scope whole-repo

Package-scoped reviews are blind to the findings that matter most. In one round, four package-scoped audits each returned clean while a systemic authorization gap sat between the RPC dispatcher and the command classes, visible only to a review that could see across both. Boundary bugs live *between* components.

### Demand evidence proportional to the claim

Every finding needs a trace from a named entry point to a named sink. Anything above informational needs something that runs. A "proof" that only asserts a substring appears in the source is not a demonstration; if a finding cannot be shown, report it as a structural concern, marked unverified, without a severity.

### Re-verify before reporting

Record the commit audited and diff it against `HEAD` before publishing. In one round, five of eleven findings were fixed within an hour of the run finishing and the report asserted them for another week. Stale findings spend reviewer attention on work already done.

### Triage into four buckets

- **REAL**: crosses a boundary above, exploitable as described. Fix now.
- **REAL-LOW**: crosses a boundary with bounded impact. Fix opportunistically; don't let it displace REAL.
- **Threat-model misaligned**: crosses no boundary. Retract, or argue explicitly with the model. A misalignment that recurs across rounds belongs in an `# AUDIT:` comment at the site.
- **Structural**: nothing exploitable today. The code's safety rests on per-site discipline that a future edit will silently break. Fix it when the fix makes the invariant hold by construction.

### Run rounds in cadence

Rounds compound. A whole-codebase round found a pre-authentication administrative takeover that a preceding component-scoped review could not see; a later round caught documentation drift an earlier one had introduced. Three cheap rounds across a release beat one thorough audit at the end.

## Filing a finding

1. Check the boundaries above. If the flow crosses none, it is most likely threat-model misaligned. Write up the boundary argument, then retract or disagree explicitly.
2. Search the source for a `# SECURITY:` or `# AUDIT:` comment at the site. If one exists and its reasoning does not actually defend the flow you found, that is a real finding, and a good one.
3. For anything exploitable, report privately to **security@abilian.com** per the [Security Policy](../reference/policies/security-policy.md). For a stale or wrong rationale in the catalogue, open a normal issue or pull request.

## Related

- [ADR 010: Security and Resilience](adrs/010-security-and-resilience.md), the umbrella pointing at each concern's decision
- [ADR 011: Data Encryption and Protection](adrs/011-encryption.md)
- [ADR 041: Privileged Operations Agent](adrs/041-privileged-operations-agent.md)
- [ADR 055: App-Runtime UID Separation](adrs/055-app-runtime-uid-separation.md)
- [Security](../guides/security.md): the operator-facing view
