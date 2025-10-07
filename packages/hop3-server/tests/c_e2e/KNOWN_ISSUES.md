# Known Issues with E2E Tests

## Issue: `auth:login` returns HTTP 400 Bad Request

**Status**: Active Bug
**Severity**: Blocks E2E tests
**Discovered**: 2025-10-07

### Symptoms

When running `hop3 auth:login username password` via hop3-cli:
- Command exits with code 0
- stderr shows: `Error: 400 Client Error: Bad Request for url: http://localhost:XXXXX/rpc`
- No token is returned

### What Works

- ✓ `hop3 auth:register` - works correctly
- ✓ `hop3 help` - works correctly
- ✓ Other non-auth commands work
- ✓ SSH tunnel connection works

### Root Cause

The RPC request for `auth:login` is being rejected by the server with HTTP 400. This suggests:
1. Parameter mismatch between CLI and server
2. Request format issue in the RPC layer
3. Server-side validation error

### Reproduction

```bash
export HOP3_DEV_HOST=your-server
hop3 auth:register testuser test@example.com testpass123  # Works
hop3 auth:login testuser testpass123  # Fails with 400
```

### Debugging Steps Tried

1. ✓ Verified SSH connection works
2. ✓ Verified hop3-cli is installed correctly
3. ✓ Verified server is responding to RPC requests
4. ✓ Verified auth commands are registered
5. ✓ Verified auth:register works
6. ❌ Server logs not accessible for debugging

### Workaround

For E2E tests, you can:

**Option 1: Skip authentication tests**
```bash
pytest packages/hop3-server/tests/c_e2e/ -v -s -k "not auth"
```

**Option 2: Manual token setup**
1. SSH to server and generate token manually:
   ```bash
   ssh your-server
   cd /path/to/hop3
   python -c "from hop3.server.security.tokens import create_token; print(create_token('testuser', scopes=['authenticated']))"
   ```

2. Set token in environment:
   ```bash
   export HOP3_API_TOKEN="your-token-here"
   ```

3. Run E2E tests

**Option 3: Test without authentication**
Temporarily disable auth on the server:
```bash
ssh your-server
export HOP3_ENABLE_AUTH=false
hop-server restart
```

### Next Steps

1. Add RPC request/response logging to hop3-cli for debugging
2. Check server-side handling of auth:login command
3. Verify parameter passing from CLI → RPC → Command
4. Add integration tests that bypass hop3-cli to isolate the issue

### Related Files

- `packages/hop3-cli/src/hop3_cli/main.py` - CLI entry point
- `packages/hop3-cli/src/hop3_cli/client.py` - RPC client
- `packages/hop3-server/src/hop3/commands/auth.py` - AuthLoginCmd
- `packages/hop3-server/tests/c_e2e/conftest.py` - E2E test setup

### Testing Status

- [x] Diagnostic script identifies the issue
- [ ] Root cause identified
- [ ] Fix implemented
- [ ] E2E tests passing with authentication

---

*This is a temporary issue tracker for E2E test development. Once resolved, this file can be deleted.*
