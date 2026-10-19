# Contributing

Start with the [README](README.md), [Phase 3 design](docs/phase3-design.md), and [measured limitations](PHASE3_EVENT_RECALL_REPORT.md).

For significant matching or architecture changes, explain the problem, design options and trade-offs before implementing. Preserve existing behavior and real failure cases; do not remove tests or relabel diagnostic cases merely to improve metrics.

- Python 3.11, typed functions, asynchronous database access and focused modules. Existing Python comments/docstrings are in Chinese; public-facing documentation is English.
- Keep bge-m3 and the current storage/clustering architecture unless a measured comparison supports a change.
- Add focused regression coverage for behavioral changes. Use the isolated test database and temporary vector collections described in the README.
- Report LLM nondeterminism, external-service prerequisites and any tests not run. Paid/live evaluations must be explicit.
- Keep credentials, operational databases and unlicensed source material out of contributions. Discuss new dependencies and source/data licenses.
- Describe the observed problem, resulting behavior, validation and remaining limitations in each change. Separate code, measurements and documentation where useful.

There is currently no project code license or contributor license agreement. Agree on licensing before accepting third-party contributions intended for redistribution.
