---
date: 2026-05-01
template: blog_post.html
description: Transparent review of our internal security audit findings and fixes.
tags:
  - Security
  - Engineering
---

# Internal Security Audit: What We Found and Fixed

Security isn't something you add at the end—it needs to be built in from the start. But even with best intentions, vulnerabilities slip through. We recently conducted an internal security audit of Hop3 and want to share what we found, what we fixed, and what we learned.

## Why Audit Our Own Code?

Three reasons:

1. **Fresh perspective**: After months of development, you stop seeing the obvious
2. **Documentation**: Forces you to document security assumptions
3. **Transparency**: Users deserve to know the security posture

We followed a structured approach, examining authentication, authorization, input validation, cryptography, and infrastructure.

## What We Found

### Critical: Command Injection (Fixed)

**The vulnerability:**

```python
# Before: Vulnerable to command injection
def install_packages(packages: list[str]) -> None:
    package_list = " ".join(packages)
    subprocess.run(f"apt-get install -y {package_list}", shell=True)
```

If `packages` contained `["nginx; rm -rf /"]`, the shell would execute both commands.

**The fix:**

```python
# After: Safe list-based execution
def install_packages(packages: list[str]) -> None:
    subprocess.run(["apt-get", "install", "-y", *packages])
```

By passing a list instead of a string with `shell=True`, the arguments are properly escaped. We swept the OS plugins, platform utilities, and certificate handling for the same pattern, and added a shared `run()` helper in `lib/shell.py` that refuses `shell=True` outright so the mistake can't creep back in.

### High: No Rate Limiting on Auth Endpoints

**The issue:** Authentication endpoints accepted unlimited login attempts, which makes online password guessing cheap.

```python
@post("/auth/login")
async def login(request: Request) -> Response:
    username = request.json["username"]
    password = request.json["password"]
    # No rate limiting!
    if verify_credentials(username, password):
        return create_session(username)
    return Response(status_code=401)
```

**The fix:** A small in-process sliding-window limiter, keyed by client IP, now sits in front of `/auth/login` and the magic-link redemption endpoint. Five attempts per IP per minute; the sixth gets a `429` with a `Retry-After`:

```python
# server/security/rate_limit.py
_AUTH_RATE_LIMITER = RateLimiter(max_requests=5, window_seconds=60.0)

@post("/auth/login")
async def login(request: Request) -> Response:
    try:
        _AUTH_RATE_LIMITER.check(_client_ip(request))
    except RateLimitError as e:
        return Response(status_code=429, headers={"Retry-After": str(int(e.retry_after))})
    ...
```

The limiter is in-memory, which is the right shape for a single-server PaaS. A multi-server deployment would back it with Redis instead — the interface is the same.

### High: Long Session Lifetime

**The issue:** Tokens lived far longer than they needed to, widening the window in which a leaked token is useful to an attacker.

**The fix:** JWT expiry now defaults to 24 hours, configurable for operators who need a different trade-off:

```python
# config.py — HOP3_TOKEN_EXPIRY_HOURS, default 24
@property
def HOP3_TOKEN_EXPIRY_HOURS(self) -> int:
    """JWT token expiry in hours."""
    return self._config_loader.get_int("HOP3_TOKEN_EXPIRY_HOURS", 24)
```

### Medium: Bearer Token Case Sensitivity

**The issue:** the `Bearer` scheme was matched case-sensitively, rejecting `bearer` or `BEARER` from otherwise-valid clients.

```python
# Before
if not auth_header.startswith("Bearer "):
    return False

# After (server/guards.py) — RFC 7235: the auth-scheme is case-insensitive
if auth_header[:7].lower() != "bearer ":
    return False
return bool(validate_token(auth_header[7:].strip()))
```

RFC 7235 specifies case-insensitive scheme matching, so a strict prefix check is a spec violation as much as a usability bug.

## What We Did Well

Not everything was bad. The audit also identified strengths:

### Proper Cryptography

- **Password hashing**: bcrypt (default work factor 12)
- **Token signing**: HMAC-SHA256 (HS256)
- **Credential encryption**: Fernet (AES-128-CBC + HMAC-SHA256)
- **Key derivation**: PBKDF2-HMAC-SHA256, 600,000 iterations with a per-install salt (the OWASP baseline)

The key-derivation scheme is versioned. Older installs were written with a static salt and 100,000 iterations; they're still readable, and `hop3 admin reencrypt-credentials` migrates them to the current scheme rather than silently leaving them weak.

### Archive Extraction Protection

An uploaded source tarball is attacker-controlled, so `lib/archives.py` gates every member before anything touches disk. Each entry is validated, then streamed out one at a time with a running byte count, so a malicious archive is rejected without being fully written:

```python
def _validate_member(member: tarfile.TarInfo, target_dir: Path) -> None:
    name = member.name

    # Reject NUL / newline filenames.
    if any(ch in name for ch in ("\0", "\r", "\n")):
        raise ValueError(f"Malicious filename detected: {name!r}")

    # Symlinks and hardlinks can point outside the sandbox; refuse both.
    if member.issym() or member.islnk():
        raise ValueError(f"Archive contains a link entry {name!r}; refused.")

    # Only regular files and directories — no devices, no FIFOs.
    if not (member.isfile() or member.isdir()):
        raise ValueError(f"Archive entry {name!r} has unsupported type.")

    # Tar slip: the resolved path must stay under the target directory.
    member_path = (target_dir / name).resolve()
    if target_dir not in member_path.parents and member_path != target_dir:
        raise tarfile.TarError(f"Attempted path traversal: {name!r}")
```

Protection against:
- **Tar slip**: paths escaping the destination (`../../../etc/passwd`) are rejected on the resolved path, so they don't escape even through symlinked parents.
- **Link attacks**: symlink and hardlink entries are refused outright, rather than trusted.
- **Decompression bombs**: extraction aborts once the running uncompressed total crosses a configurable limit (`HOP3_MAX_EXTRACTED_SIZE`), and once the member count crosses `HOP3_MAX_ARCHIVE_MEMBERS` — neither trusts the archive's own headers.

### Input Sanitization

Every user-controlled string that ends up in a shell payload, a filesystem path under the app root, or a proxy config file passes through a validator in `core/identifiers.py` before it leaves the RPC boundary. App names are the canonical example:

```python
# Starts and ends with an alphanumeric, hyphens/underscores in between, 3-63 chars.
APP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]$")

def validate_app_name(name: str) -> str:
    if not APP_NAME_RE.fullmatch(name):
        raise InvalidIdentifierError(
            f"Invalid app name {name!r}: must be 3-63 characters, start and "
            f"end with a letter or digit, and contain only letters, digits, "
            f"hyphens, and underscores."
        )
    return name
```

The constraint is deliberately tight: a name that's safe as a filesystem path segment and as a Docker Compose service identifier can't carry a `..`, a leading dash, or a shell metacharacter. The same module validates env-var keys and hostnames the same way.

### Security-Focused Tests

The point of all this is that none of it can quietly regress, so each guard has its own test that asserts the *rejection*, not just the happy path:

```python
def test_rejects_path_traversal():
    """Verify tar slip protection."""
    malicious_tar = create_tar_with_path_traversal()
    with pytest.raises(tarfile.TarError, match="path traversal"):
        extract_archive_to_dir(malicious_tar, temp_dir)

def test_rejects_link_entries():
    """Verify symlink/hardlink protection."""
    malicious_tar = create_tar_with_symlink()
    with pytest.raises(ValueError, match="link entry"):
        extract_archive_to_dir(malicious_tar, temp_dir)
```

## What We Shipped, and What We Deferred

The findings above are all addressed in the current codebase: command injection is closed by list-based execution, auth endpoints are rate-limited, token lifetime is down to a day, and the bearer-token scheme match is case-insensitive. Alongside those fixes, the audit drew a clear line around what we deliberately have *not* built yet.

Multi-factor authentication is the largest of these. Its design is written down in [ADR 012](https://github.com/abilian/hop3/blob/main/notes/adrs/012-mfa.md) — TOTP first, hardware tokens and biometrics layered on later — but it is deferred, not implemented. The intended deployment pattern already gives operators a second factor in practice: the CLI reaches the server over an SSH tunnel, so RPC access is gated by the operator's SSH key on the host. MFA hardens the password-login path on top of that, and we'll adopt the ADR's design when account-level MFA becomes a requirement rather than describe it as if it were live.

Two more hardening items remain on the roadmap rather than in the code: a structured audit log of security-relevant events, and CSRF protection for the dashboard's session-cookie flows. We name them here so the gaps stay in plain sight, where a reader can hold us to them.

## Lessons Learned

### 1. `shell=True` is Almost Always Wrong

If you're constructing shell commands from user input, use list-based subprocess calls:

```python
# Bad
subprocess.run(f"command {user_input}", shell=True)

# Good
subprocess.run(["command", user_input])
```

### 2. Security Defaults Matter

A long-lived token and an unthrottled login endpoint are not exotic vulnerabilities — they're defaults nobody revisited. Tightening the token lifetime and adding per-IP rate limiting cost little, and both now ship out of the box. Users shouldn't have to configure security; the secure choice should be the one they get for free.

### 3. Test Security Explicitly

Don't rely on functional tests to catch security issues. Write explicit security tests:

```python
def test_sql_injection_prevented():
    """Verify SQL injection is prevented."""
    result = app_repo.get_by_name("'; DROP TABLE apps; --")
    assert result is None  # Not an error, just no match
```

### 4. Document Security Assumptions

Every security-relevant function should document its assumptions:

```python
def create_token(username: str) -> str:
    """Create a signed JWT token.

    Security assumptions:
    - HOP3_SECRET_KEY is a cryptographically random string
    - HOP3_SECRET_KEY is kept secret and not logged
    - Token lifetime is short enough to limit exposure
    """
```

## Ongoing Security Practices

After this audit, we established ongoing practices:

1. **Dependency scanning**: Automated checks for known vulnerabilities
2. **Code review focus**: Security checklist for PRs
3. **Regular audits**: Quarterly internal reviews
4. **Responsible disclosure**: Security policy and contact

## Report Your Findings

Found a security issue? Please report it responsibly:

- Email: security@abilian.com
- We'll acknowledge within 48 hours
- We'll work with you on coordinated disclosure
