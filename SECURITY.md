# Security

GIIM is a locally validated research/portfolio application, not a hardened multi-tenant service. A repository publication is separate from deploying the application.

- Keep `.env`, API keys, database exports and model caches outside Git. Use the placeholder templates and generate unique local credentials.
- The development Compose services bind to loopback. Never expose PostgreSQL or Qdrant directly to the internet.
- Treat retrieved articles as untrusted input. Structured validation, exact citations and a claim-support check reduce risk; they do not guarantee truth or eliminate prompt injection.
- Ingestion/admin routes require a bearer token. Production requires a token of at least 32 characters. The basic in-process rate limiter is not distributed abuse protection.
- Run tests against a separate database whose name ends in `_test`. Never run restore, cleanup or legacy mutation tools against valuable data without a backup.
- The dependency lock pins versions but is not hash-verified; security updates and a dependency/vulnerability review remain ongoing maintenance work.

## Reporting a vulnerability

Do not publish credentials, private data or exploit details in an ordinary GitHub issue. Use GitHub private vulnerability reporting if the owner has enabled it. If unavailable, request a private reporting channel without including sensitive details. No response-time SLA or bug bounty is offered.

If a credential enters Git, revoke/rotate it before considering history cleanup. Deleting it from the latest tree does not remove it from older commits, forks or clones. History rewrites require owner approval and coordination.
