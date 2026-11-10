# Meaningful verification map

This maps new component responsibilities to tests that actually ran. It is not a line-coverage report; the pinned analyst environment does not include coverage instrumentation.

| Component | Executed evidence |
|---|---|
| MCP `config`, `inputs`, `models`, `normalize`, `adapter` | Tool/schema/invalid-input cases; actual API integer IDs/timestamps/wrapped lists; safe origins/source URLs; licensing/summary and truncation tests |
| MCP `rest` | 404/422/429/502/503/504/401/redirect mapping, timeout/recovery/retry counts, malformed and oversized payloads, forbidden routes |
| MCP `server`, `http`, `__main__` | Official in-process discovery/calls, subprocess stdio, actual authenticated HTTP invocation of every tool, authorization/origin/exposure rejection |
| MCP `fixtures`, `demo` | All 24 evaluation cases, six exact functional scenarios, actual protocol tests; fixtures are explicitly scripted/authored |
| Agent `runtime`, `coordinator`, `roles`, `gateway`, `hooks`, `schemas` | Real ADK Runner role/state/tool flow; structured schema failures; approving/rejecting verifier; one revision; unauthorized tools; live opt-in/constructor checks |
| Agent `ledger`, `security`, `budget` | Wrong event/article/publisher/URL; altered quotes; incomplete/withheld/stale support; omitted conflict; injection; tool/model/token/time bounds; concurrent-session isolation |
| Agent `fake` | Normal/evolving/multilingual/refusal/conflict scenarios; simultaneous corrupt references; forced valid-but-irrelevant results; unknown real-news identities |
| Agent `trace`, `logging`, `config`, `stats` | Synthetic reported token/cost arithmetic; canary redaction/file permissions; unknown/missing pricing; external exception filtering; empty/incomplete/malformed trace summary |
| Agent `eval` | Dataset/category/schema checks and complete executed 24-case runner with provenance and actual outputs |
| Agent `__main__`, `adk_entry`, `adk_app` | Installed CLI normal/refusal; official `adk run`; local `adk web` session creation and `/run` response, final-output-only boundary |
| Summary/sampling/acceptance scripts | Summary executed against generated evaluation and acceptance traces; sampling verified in initial implementation; acceptance runner rerun over controlled and actual APIs and installed wheels |
| Packaging/Docker | Fresh non-editable installation, `pip check`, non-root image, installed-wheel 107-test suite |
| Optional backend fixture harness | Existing seed/smoke scripts previously run against isolated stores; portable Compose config previously validated. Not a second full portable-stack deployment certification. |

The original root `tests/` suite was not edited. HTTP transport test expansion preserves the earlier event-excerpt assertion while adding the other four tools. Four new acceptance regressions increase the new-suite count from 103 to 107.
