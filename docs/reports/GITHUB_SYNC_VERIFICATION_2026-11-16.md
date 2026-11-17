# GitHub synchronization verification — November 16, 2026

Verified source baseline: `7a5bc122dffa815f15d979278f1d5f1523d6b6b6`, branch `feature/mcp-agent`, initially clean. Remote: [qida866/giim](https://github.com/qida866/giim). Fetch and `ls-remote --heads` found only remote `main`, at `651ffbc1a038c76c7c0d74be30bcc2b4538faf4d`, unchanged from the previous public release. The local feature branch has 19 committed updates beyond that public baseline. It initially tracks `origin/main`; an unqualified push is therefore inappropriate.

The latest Agent/MCP changes are already committed but were not on GitHub at inspection. No automated release workflow exists in `.github`; `CONTRIBUTING.md` requires preserving architecture, tests and licensing boundaries. Phase 3 was published through `release/phase3-public`. Local `main` contains separate research history and is not the source for this synchronization. Task 1 remains separately committed on `feature/gcp-deploy`; its four commits are not ancestors of this branch and are not silently merged or published here.

Publishing `feature/mcp-agent` as a same-named remote branch requires the user's branch decision because only `main` currently exists remotely and updating main was not authorized. This report records the pre-publication verification; final push status and exact remote SHA must be confirmed with Git after any authorized push. No default-branch change, merge, force-push or history rewrite is part of this work.

## Implementation findings

| Capability | Current implementation evidence | Qualification |
|---|---|---|
| Multilingual semantic retrieval | `apps/api/src/embedding/client.py`, `vector_sync.py`, search router and Qdrant integration | Default local BAAI/bge-m3 dense embeddings; no new model or NLP feature added |
| Cross-lingual event matching | Existing multilingual retrieval, clustering, story matching/review/consolidation services | Semantic matching groups reports; ingestion deduplication separately uses publisher-scoped URL/content/normalized-title checks, not an arbitrary cross-language duplicate classifier |
| Participant/action constraints | `apps/api/src/services/story_review.py` full-member review, primary-action audit and participant-set checks | Existing constraints retained; contextual over-merging remains a documented limitation |
| LLM verification | Story review, story brief and claim verification services | Existing Phase 3 path unchanged; optional Agent uses separate Gemini integration |
| Agent/MCP | `apps/agent`, `apps/mcp_server`, strict ledger, budget/retry wrapper and ADK Coordinator | Five read-only REST-backed tools; exact evidence associations, source excerpt policy and uncertainty retained |
| Historical accuracy figures | `evaluation/phase3-summary.json` and `PHASE3_EVENT_RECALL_REPORT.md` agree | 95→115 true positives, 51→31 false negatives, 4→0 scored false positives; **not rerun today** |

The existing matching/retrieval/ingestion services, original tests and historical aggregate results have no diff from the public Phase 3 baseline. The incoming branch restores two previously omitted model modules required by Phase 3 imports, adds the Agent/MCP packages and tests, and contains reviewed synthetic evidence and documentation. Its full file manifest is retained with this verification. No matching accuracy metric is relabeled as newly measured. No public deployment or universal language coverage claim is made.

## Fresh executed checks

- **175 Agent/MCP tests passed**, three existing dependency deprecation warnings. Ruff check and format check passed; agent environment `pip check` passed.
- **130 original backend tests passed**, two existing paid-provider tests deselected, one existing structlog warning. Separate backend environment `pip check` passed.
- All **180 tracked Python files parsed successfully**. No source files changed to obtain a pass.
- Root Compose configuration validated using `.env.example` and `--no-env-resolution`. A normal config attempt first reported the deliberately absent private `.env`; no file was created and no credentials were printed. This validates structure/interpolation, not new production startup or secret provisioning.
- Existing passing live Gemini evidence remains historical: all five controlled scenarios achieved a pass across staged runs, with A/B last run November 11. No paid model/API call was made for this synchronization.

The component suite ran in the existing pinned local image with current sources and external networking disabled. Backend tests used the separate `giim-mcp-test` stack, isolated test database, temporary vector collections and cached bge-m3, with provider keys blank and model downloads disabled. No application database was recreated, reseeded or deleted. These checks establish the executed regression results, not exhaustive absence of regressions or compatibility with freshly downloaded dependencies.

### Exact verification commands

From the `feature/mcp-agent` worktree:

```sh
git status --short --branch
git branch -vv
git log --oneline --decorate -12
git fetch origin
git ls-remote --heads origin
git diff --name-status origin/main..HEAD
docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint sh giim-agent-task2-ab-ready:local \
  -c 'ruff check apps/agent apps/mcp_server scripts/live_gemini_trial.py && ruff format --check apps/agent apps/mcp_server scripts/live_gemini_trial.py && python -m pytest -q -p no:cacheprovider -c apps/agent/pyproject.toml apps/agent/tests apps/mcp_server/tests && pip check'
docker compose --env-file .env.example config --no-env-resolution --quiet
```

From the existing private sibling `mcp-validation` workspace:

```sh
docker compose -p giim-mcp-test -f compose.yml --env-file .env run --rm -T \
  -e GOOGLE_API_KEY= -e DEEPSEEK_API_KEY= \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  api python -m pytest -q -p no:cacheprovider \
  -k 'not test_chat_basic and not test_chat_with_system_message'
docker compose -p giim-mcp-test -f compose.yml --env-file .env run --rm -T --no-deps api python -m pip check
```

Python's `ast.parse` checked every tracked `.py` file without generating caches. Complete regression outputs, incoming path manifest and the scoped security scan are under [verification evidence](../evidence/github-sync-20261116/).

## Publication boundaries and remaining issues

The candidate worktree and all blobs reachable from this branch were checked against available private credential values and high-confidence key patterns without displaying values. Incoming history was separately checked for private environments, datasets, database/cache files and excluded development notes. No findings were detected by those checks. `.runs`, private `.env`, model cache, databases and private research data remain excluded; intentionally reviewed synthetic reports/test outputs remain included. Existing public history retains previously documented legacy examples and author metadata; no history cleanup was attempted. This is a scoped scan and content review, not a guarantee of exhaustive secret discovery or licensing clearance.

Only README, the outdated architecture status paragraph and verification documentation/evidence are newly changed in this synchronization task. Production readiness, broad model quality, live retry recovery and restricted historical-corpus reproduction remain unverified. The project still has no general code license; no license is added here. Publishing this feature branch will not put Agent/MCP on GitHub's default `main` page; that would require a separately approved merge. The independent GCP branch also remains outside this synchronization.
