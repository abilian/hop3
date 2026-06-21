---
date: 2026-04-03
template: blog_post.html
description: JWT tokens, SSH tunneling, and magic link authentication.
tags:
  - Security
  - Engineering
---

# The Auth Problem: Securing a Self-Hosted PaaS

Authentication in a PaaS is tricky. You're protecting access to applications, databases, secrets, and server configuration. Get it wrong and someone deploys crypto miners to your infrastructure. Get it too right and developers can't do their jobs.

We spent a lot of time thinking about this. Kubernetes punts to external identity providers. Heroku has a global account system. Neither fit our single-server model. We needed something that works standalone, leverages existing infrastructure, and doesn't require a PhD in OAuth to set up.

Here's what we built.

## The Guiding Ideas

Before writing code, we established some principles:

1. **No central auth server**—Hop3 runs on a single server; auth should too
2. **Leverage existing keys**—Developers already have SSH keys; use them
3. **Stateless where possible**—JWT tokens avoid server-side session management
4. **Fail closed**—Invalid tokens are rejected, never ignored
5. **Multiple access methods**—CLI, web, API should all work

## SSH: The Obvious Choice (That Wasn't Obvious)

When we looked at how developers would actually use Hop3, the CLI dominated. And for CLI access, SSH is already solved.

```bash
hop3 app list
```

What happens under the hood:

1. The CLI opens an SSH connection using your existing keys or agent
2. An SSH tunnel forwards JSON-RPC traffic to `hop3-server`
3. The server trusts connections from localhost (they came through SSH)
4. No passwords, no tokens—your SSH key is your identity

This felt almost too simple. But consider: if you can SSH to a server, you already have the access Hop3 needs. We're not adding security theater; we're reusing infrastructure that already exists and already works.

The flow looks like this:

```
┌─────────────┐         ┌─────────────────┐
│  hop3 CLI   │         │   hop3-server   │
└──────┬──────┘         └────────┬────────┘
       │                         │
       │  1. SSH connection      │
       │─────────────────────────▶
       │                         │
       │  2. Open tunnel to      │
       │     localhost:8000      │
       │─────────────────────────▶
       │                         │
       │  3. JSON-RPC call       │
       │     hop3 app list
       │─────────────────────────▶
       │                         │
       │  4. Response            │
       │◀─────────────────────────
```

## JWT Tokens for Everything Else

SSH works great for interactive CLI sessions. But what about:

- The web dashboard?
- CI/CD pipelines without SSH access?
- API integrations?

For these, we use JWT tokens:

```python
def create_token(username: str, scopes: list[str], expires_hours: int = 24) -> str:
    """Create a signed JWT token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "scopes": scopes,
        "iat": now,
        "exp": now + timedelta(hours=expires_hours),
        "jti": secrets.token_urlsafe(16),  # Unique token ID for revocation
    }
    return jwt.encode(payload, get_secret_key(), algorithm="HS256")
```

Tokens are signed with HMAC-SHA256, expire after 24 hours by default (configurable via `HOP3_TOKEN_EXPIRY_HOURS`), and include a unique identifier (`jti`) so we can revoke them if needed.

Why JWT instead of session cookies? Simplicity. JWTs are self-contained—the server doesn't need to look anything up to validate them. This matters when you want to add API access or multiple server instances later.

## The Magic Link Trick

Here's a usability problem: you want to open the web dashboard, but you don't have a password (you've been using SSH). Do you create a password just for web access?

We took inspiration from Slack and others: magic link login.

```bash
# On your machine (with SSH access)
hop3 login --web

# Output:
# Open this URL in your browser:
# https://myserver.com/auth/magic/eyJhbGciOiJIUzI1NiIs...
```

The flow:

1. CLI calls `auth magic-link` via SSH (authenticating with your key)
2. Server generates a single-use token with 5-minute expiry
3. You open the URL in your browser
4. Server validates the token, revokes it, creates a session, redirects to dashboard

No password needed. If you have SSH access, you can get web access. The token is single-use and short-lived, so sharing the URL is relatively harmless.

## Password Hashing (When You Need Passwords)

Some users want password auth—maybe they're accessing from a machine without their SSH keys. We support that too:

```python
import bcrypt

def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12)
    ).decode("utf-8")
```

We use bcrypt at cost factor 12 (ADR 014), deliberately slow per guess. That tunable work factor is what makes offline brute-force against a leaked hash impractical, and it can be raised as hardware gets faster.

## Protecting Secrets

Hop3 stores database credentials, API keys, and other sensitive data. We encrypt these at rest:

```python
from cryptography.fernet import Fernet

def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential using Fernet (AES-128-CBC + HMAC)."""
    key = derive_key_from_secret()
    fernet = Fernet(key)
    return fernet.encrypt(plaintext.encode()).decode()
```

Fernet provides authenticated encryption—both confidentiality (can't read it) and integrity (can't tamper with it). The encryption key is derived from `HOP3_SECRET_KEY` with PBKDF2-HMAC-SHA256, which brings us to...

## The One Secret to Rule Them All

Everything depends on a single signing secret. Its canonical home is a secrets-tier file the installer writes, read identically by the running service and the local `su-hop3` CLI:

```bash
# /etc/hop3/secret-key  (root:hop3, mode 0640)
```

For tests, overrides, and legacy installs, the same value can be supplied through the `HOP3_SECRET_KEY` environment variable instead. Either way, this one secret signs JWT tokens and derives the credential-encryption key. Guard it carefully. Back it up. Don't commit it to git.

Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Token Revocation

JWTs are stateless, but sometimes you need to revoke a token before it expires (compromised key, user leaving, etc.). We handle this with a simple blacklist:

```python
def validate_token(token: str) -> dict:
    """Validate and decode a JWT token."""
    payload = jwt.decode(token, get_secret_key(), algorithms=["HS256"])

    if is_token_revoked(payload["jti"]):
        raise InvalidTokenError("Token has been revoked")

    return payload
```

Revoked tokens are stored in the database, each row carrying the token's original `expires_at`. That timestamp is what lets the list stay bounded: once a revoked token would have expired on its own, its blacklist entry is safe to prune—there's no point tracking tokens that are already invalid.

## Authorization Scopes

Tokens carry scopes that limit their capabilities:

```python
# Scopes accepted on the general bearer-auth path
VALID_SCOPES = {"authenticated", "admin", "user"}
```

The `magic_link` scope is deliberately *not* in this set. Magic-link tokens are validated by a separate single-use path, never by the general bearer check—otherwise a redeemable magic link could act as a five-minute bearer token for any RPC command. Keeping the scopes apart is what makes that guarantee enforceable.

The general scopes let us reason about capability per token: an `admin`-scoped token can do administrative work, while an ordinary `authenticated`/`user` token cannot. As scoped policies grow, the same mechanism is how we'd issue narrower tokens (for example, a CI token that can deploy but not manage users).

## What We're Still Working On

It helps to be clear about where the model stops. Here's what isn't built out yet:

- **No MFA**: Multi-factor auth is designed but deferred (ADR 012). Today the second factor is the operator's SSH key on the host—CLI access goes CLI → SSH tunnel → RPC—plus per-IP rate limiting on the web login and magic-link endpoints. TOTP gating JWT issuance is the planned first step.
- **Manual key rotation**: There's no automated rotation policy. Rotating `HOP3_SECRET_KEY` invalidates issued JWTs and sessions; stored addon credentials are re-encrypted with `hop3 admin reencrypt-credentials` rather than lost. Automated rotation is future work (ADR 011).

Rate limiting on the auth endpoints is already in place—a per-IP sliding-window counter (five attempts per minute) guards both password login and magic-link redemption—but it's deliberately in-memory and single-server; a Redis-backed limiter is what multi-server deployments will need.

## The Practical Details

Set up authentication in production:

```bash
# Required: the signing secret (file at /etc/hop3/secret-key, or this env var)
export HOP3_SECRET_KEY="generate-something-random"

# Optional: token lifetime in hours (default 24)
export HOP3_TOKEN_EXPIRY_HOURS=24
```

Try it:

```bash
# SSH-based login
hop3 login --ssh root@myserver.com

# Magic link for browser
hop3 login --web

# Show the current user
hop3 auth whoami
```

---

Authentication is one of those things you want to be boring. No surprises, no clever hacks, just predictable security. We've tried to build something that's secure by default but gets out of your way when you're trying to deploy code.

*Questions about our security model? [Open an issue](https://github.com/abilian/hop3/issues) or check the [security policy](/reference/policies/security-policy/).*
