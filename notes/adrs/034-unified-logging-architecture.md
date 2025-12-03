# ADR 034: Unified Logging Architecture

**Status**: Pre-Draft (For Discussion)
**Date**: 2025-12-03
**Related ADRs**: ADR 033 (WAF Integration)

---

## Summary

Establish a unified logging architecture for all Hop3 components, providing consistent log management, rotation, and access patterns across application logs, WAF audit logs, system logs, and future log streams.

---

## Context

Hop3 currently has ad-hoc logging:
- Application stdout/stderr captured by uWSGI
- System operations use `hop3.lib.log()` function
- No structured logging format
- No unified rotation or retention policy

With the addition of WAF (ADR-033), we need:
- WAF audit logs (JSON, high volume under attack)
- Firewall action logs
- Potentially more log streams in the future

This is an opportunity to establish a consistent logging pattern.

---

## Proposed Log Streams

| Stream | Purpose | Format | Volume |
|--------|---------|--------|--------|
| `apps/<app>/` | Application stdout/stderr | Text | Variable |
| `waf/` | WAF audit events | JSON | High under attack |
| `firewall/` | IP block/unblock events | JSON | Low-medium |
| `system/` | Hop3 server operations | JSON | Low |
| `access/` | HTTP access logs (optional) | CLF/JSON | High |

---

## Key Questions

1. **Library**: loguru vs structlog vs stdlib logging?
2. **Storage**: Flat files vs SQLite for queryable logs?
3. **Rotation**: Size-based, time-based, or both?
4. **Retention**: Per-stream retention policies?
5. **Access**: CLI (`hop3 logs`), API, or both?
6. **Centralization**: Support for external log aggregators (syslog, fluentd)?

---

## Strawman Proposal

### Use loguru with JSON output

```python
from loguru import logger

# Configure per-stream loggers
waf_logger = logger.bind(stream="waf")
waf_logger.add(
    "/var/hop3/log/waf/audit.log",
    format="{message}",  # JSON already formatted
    rotation="100 MB",
    retention="30 days",
    compression="gz",
)
```

### Unified Log Directory Structure

```
/var/hop3/log/
├── apps/
│   ├── myapp/
│   │   ├── web.log
│   │   └── worker.log
│   └── otherapp/
│       └── web.log
├── waf/
│   └── audit.log
├── firewall/
│   └── actions.log
└── system/
    └── hop3.log
```

### CLI Access

```bash
hop3 logs                      # All recent logs
hop3 logs myapp                # App logs
hop3 logs --stream=waf         # WAF logs
hop3 logs --stream=waf --json  # Raw JSON output
hop3 logs --follow             # Tail mode
```

---

## Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **loguru** | Simple API, built-in rotation, Python-native | Another dependency |
| **structlog** | Structured logging, composable | More complex setup |
| **stdlib** | No dependencies | Verbose, rotation needs extra config |
| **SQLite** | Queryable, indexed | More complex, storage overhead |

---

## Decision

**Deferred** - To be discussed after WAF Phase 1 implementation.

For WAF Phase 1, we will use loguru with JSON output as a proof-of-concept, which can be refactored into the unified architecture later.

---

## References

- [loguru documentation](https://loguru.readthedocs.io/)
- [structlog documentation](https://www.structlog.org/)
- [12-Factor App: Logs](https://12factor.net/logs)
