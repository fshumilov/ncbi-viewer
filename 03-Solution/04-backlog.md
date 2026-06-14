# Implementation backlog — GEO Expression Service

## Purpose

Ordered work for Phase 7+; one testable vertical increment per slice group; subordinate to `03-architecture.md` and `02-feature-slices.md`. Each item names concrete modules and routes from the architecture — implement top-to-bottom, respecting **Blocked by**.

## References

- Architecture: `03-Solution/03-architecture.md`
- Feature slices: `03-Solution/02-feature-slices.md`
- Solution draft (scope + acceptance): `03-Solution/01-solution-draft.md`
- Task spec: `../task/GEO_EXPRESSION_SERVICE_SPEC.md`
- Stakeholders: `01-Context/01-stakeholders.md`
- **Not yet authored:** `02-Requirements/02-system-requirements.md`, `04-UI/` (deferred — API-first; no mockup-plan screen ids)

## How to use

Implement items in **Order** (summary table). Within a slice group, complete tasks in listed order. Respect **Blocked by** before starting an item. In Phase 7 step 18, pick the next `not started` item, set its **Status** to `in progress`, check off **Tasks**, and set `done` when every **Done when** bullet passes. Update this file when behavior or module layout changes. After BL-02: **BL-03 (cache) → BL-05 (chat) → BL-04 (resilience) → BL-06** — chat before GeoClient hardening per [implementation decisions](#implementation-decisions-2025-06-14); BL-04 remains in assessment MVP.

## Backlog summary

| Order | Slice | Item ids | Status | Theme (one line) | Blocked by |
| --- | --- | --- | --- | --- | --- |
| 1 | F-01 | BL-01 | done | Project scaffold, config, logging, validation, health route | — |
| 2 | F-02 | BL-02 | done | Cold-path expression: GeoClient, mapper, plotter, `GET /expression` | BL-01 |
| 3 | F-03 | BL-03 | done | Two-tier CacheStore + expression cache seam (`cached`, `duration_ms`) | BL-02 |
| 4 | F-04 | BL-05 | not started | ChatAgent, ExpressionTool, `POST /chat` (stub LLM OK) | BL-02, BL-03 |
| 5 | F-05 | BL-04 | not started | GeoClient retries, timeouts, bounded concurrency, HTTP error mapping | BL-02, BL-05 |
| 6 | F-06 | BL-06 | not started | README runbook, `.env.example`, acceptance cross-links | BL-03, BL-04, BL-05 |

## Items

### F-01 Service foundation

#### BL-01 — App shell, validation, and health

- **Slice:** F-01
- **Screens / routes:** `route.health` (`GET /health`)
- **Tasks:**
  - [x] Create `pyproject.toml` at repository root with Python 3.11+, FastAPI, uvicorn, pydantic v2, pydantic-settings, httpx, matplotlib, numpy — **no pandas** (stdlib `csv` for tabular parsing)
  - [x] Scaffold package layout: `geo_expression_service/{main.py,config.py,logging.py,exceptions.py,api/,services/,domain/,adapters/}`
  - [x] Implement `config.py` (`Settings`, `GEO_*` env prefix): cache dir placeholder, HTTP timeout, concurrency limit keys (used later)
  - [x] Implement `logging.py`: middleware assigning `request_id`; summary log format per project logging rules
  - [x] Implement `exceptions.py`: domain hierarchy (`InvalidGeneCountError`, invalid GSE format, base `GeoExpressionError`) — no bare `Exception` in handlers
  - [x] Implement `domain/validation.py`: normalize GSE to uppercase `GSE\d+`; normalize gene symbols uppercase; enforce 2–5 unique genes
  - [x] Implement `main.py`: FastAPI app factory, lifespan hook placeholder for shared httpx client
  - [x] Implement `api/routes/health.py`: `GET /health` → liveness JSON
  - [x] Wire exception→HTTP mapping in API layer (422 validation, structured error bodies)
- **Done when:**
  - `uvicorn geo_expression_service.main:app` starts without import errors
  - `GET /health` returns HTTP 200 with JSON liveness payload
  - Validation helpers reject gene count ∉ [2, 5] and malformed GSE before any GEO I/O (unit-call or route guard on a stub expression dependency)
  - Logs include `request_id` on a health request
- **Notes:** Parallel with none; blocks all downstream items. No GeoClient, cache, or chat in this item.

---

### F-02 Direct expression (cold path)

#### BL-02 — Expression pipeline and `GET /expression`

- **Slice:** F-02
- **Screens / routes:** `route.expression` (`GET /expression`)
- **Tasks:**
  - [x] Implement `domain/models.py`: `ExpressionRequest`, `GeneMappingStat`, `MappingSummary`, `PlotArtifact`, `ExpressionResult` (`cached: false`, `duration_ms` populated)
  - [x] Implement `domain/annotation_mapper.py`: column detection, `///` multi-gene split, missing/null/`---` handling, per-gene probe counts
  - [x] Implement `domain/plot_builder.py`: combined multi-gene boxplot → PNG base64 (`PlotArtifact.format = png_base64`)
  - [x] Implement `adapters/geo_client.py`: async httpx download of series matrix + GPL annotation; injectable client; no persistent cache (pass-through bytes OK); parse matrix/annotation with stdlib `csv` (not pandas)
  - [x] Implement `services/expression_service.py`: orchestration `get_expression(request)` — validate → fetch → map → plot; explicit cache adapter seam (no-op or inject stub until BL-03)
  - [x] Implement `api/routes/expression.py`: query params `gse`, `genes` (comma-separated); delegate only to `ExpressionService`
  - [x] Implement `api/dependencies.py`: DI for `ExpressionService`, shared httpx client from lifespan
  - [x] Register routes in `main.py`; OpenAPI documents `GET /expression`
- **Done when:**
  - `GET /expression?gse=GSE2034&genes=TP53,BRCA1` returns HTTP 200 with base64 plot, per-gene mapping stats, and `duration_ms` (solution draft acceptance — happy path)
  - Requests with 1 or 6 genes return HTTP 422 before GEO fetch (gene count bounds)
  - Partial/zero probe mapping returns HTTP 200 with explicit per-gene stats and `skip_reason` — no fabricated values
  - Multi-gene annotation cells (`GENE /// OTHER`) map when requested symbol present
  - Routes do not import `GeoClient` or `CacheStore` directly — only `ExpressionService`
  - `cached` is `false` on cold path (cache layers added in BL-03)
- **Notes:** Freeze `ExpressionResult` DTO at end of this item; F-04 ExpressionTool depends on stable shape. Matrix/annotation parsing uses **stdlib `csv` only** — document trade-offs in BL-06 README.

---

### F-03 Bounded two-tier cache

#### BL-03 — CacheStore and expression warm path

- **Slice:** F-03
- **Screens / routes:** `route.expression` (warm cache behavior)
- **Tasks:**
  - [x] Implement `adapters/cache_store.py`: in-memory LRU fronting disk under `GEO_CACHE_DIR`; keys `raw:{url_hash}`, `map:{gpl_id}`, `result:{gse_id}:{genes_hash}`; gene list sorted + uppercase for hash
  - [x] Add negative caching sentinel for failed GPL parse/fetch
  - [x] Implement eviction: LRU + max entries/bytes (`GEO_CACHE_MAX_ENTRIES`, `GEO_CACHE_MAX_BYTES` or architecture equivalents)
  - [x] Disk entries include `schema_version: 1`; delete-on-read mismatch
  - [x] Integrate `CacheStore` into `ExpressionService`: lookup/store all layers; promote memory←disk on hit
  - [x] Expose `cached: true/false` and measurable `duration_ms` on `ExpressionResult`
  - [x] Log cache hit/miss with `request_id`
- **Done when:**
  - First `(gse, genes)` request shows `cached: false`; identical second request shows `cached: true` and measurably lower `duration_ms` (solution draft — cache cold/warm)
  - After process restart, repeat request hits disk tier without full raw GEO re-download (restart survival)
  - Filling cache beyond configured max evicts oldest entries; service remains stable (bounded cache)
  - Negative cache: repeated request after GPL parse failure fails fast without download storm
- **Notes:** Required before BL-05 so chat repeat queries expose cache metadata.

---

### F-04 Chat agent with tool calling

#### BL-05 — ChatAgent, ExpressionTool, and `POST /chat`

- **Slice:** F-04
- **Screens / routes:** `route.chat` (`POST /chat`)
- **Tasks:**
  - [ ] Extend `domain/models.py`: `ChatRequest`, `ChatResponse` (`message`, `expression`, `tool_invoked`)
  - [ ] Implement `services/chat_agent.py`: pydantic-ai agent with **ExpressionTool** calling `ExpressionService.get_expression(...)` — same method as `GET /expression`
  - [ ] Implement stub LLM path when `OPENAI_API_KEY` absent or `GEO_STUB_LLM=true`; tool path remains real
  - [ ] Implement `api/routes/chat.py`: JSON body `{ "message": "..." }`; delegate to ChatAgent only
  - [ ] Pass through `cached`, `duration_ms`, and mapping stats from tool result into `ChatResponse`
  - [ ] Log tool invocation with parsed GSE/genes and `request_id`
- **Done when:**
  - `POST /chat` with message like *"Show me TP53 and BRCA1 expression in GSE2034"* returns HTTP 200 with assistant text + plot artifact (solution draft — chat happy path)
  - Server logs prove ExpressionTool invoked with parsed GSE and genes — not LLM-only completion (`tool_invoked: true` on happy path)
  - Grounded reply references genes/series consistent with tool output
  - Message without recognizable GSE/genes returns clarification (HTTP 200 with agent message — document behavior)
  - Stub LLM mode still runs tool and returns plot
  - Repeat chat query after BL-03 shows cache metadata in expression payload
- **Notes:** Start after BL-02 and BL-03; precedes BL-04 (resilience) per implementation decisions.

---

### F-05 GEO resilience and bounded concurrency

#### BL-04 — Harden GeoClient I/O

- **Slice:** F-05
- **Screens / routes:** `route.expression` (error paths on upstream failure)
- **Tasks:**
  - [ ] Extend `config.py`: retry count, backoff, `GEO_HTTP_TIMEOUT_S`, `GEO_CONCURRENCY_LIMIT`
  - [ ] Add retries with backoff and timeout to `adapters/geo_client.py` (httpx async only)
  - [ ] Add bounded semaphore for parallel multi-file fetches
  - [ ] Map `GeoDownloadError`, timeout, upstream failures to specific HTTP codes in API layer (404/502/504 per architecture — no hung requests)
  - [ ] Log retry/timeout events with `request_id` under load
- **Done when:**
  - Simulated slow or failing GEO response returns structured HTTP error within timeout — request does not hang (solution draft — resilience group, when present)
  - Parallel fetches respect semaphore limit observable in logs
  - No blocking `requests` usage on event loop
- **Notes:** In assessment MVP; implement after BL-05 so tool-calling path is verified before GeoClient hardening. Document retry/timeout/semaphore choices in BL-06.

---

### F-06 Documentation and runbook

#### BL-06 — README and environment template

- **Slice:** F-06
- **Screens / routes:** — (docs only; covers all routes)
- **Tasks:**
  - [ ] Author root `README.md` + `docs/run_book.md`: clean-env install, uvicorn run, both endpoints with curl examples
  - [ ] Add paragraph on gene-mapping trade-offs (aggregation, multi-gene cells, unmapped probes, **stdlib `csv` vs pandas**)
  - [ ] Add paragraph on cache layers, eviction, and negative caching
  - [ ] Document validation rules (2–5 genes, GSE format), stub LLM mode, clarification vs error behavior for chat
  - [ ] Create `.env.example` at repository root with `GEO_*` and optional LLM key
  - [ ] Cross-link solution draft acceptance checklist items verifiable via README/OpenAPI
  - [ ] Optional stretch: note recommended tests in `tests/` (mapping unit, cache speedup) without blocking MVP
- **Done when:**
  - Assessor can follow README from clean env; service starts; `GET /health`, `GET /expression`, and `POST /chat` respond
  - README contains distinct mapping and cache decision paragraphs (solution draft — documentation group)
  - `.env.example` lists all config keys used in code
- **Notes:** Finalize after BL-03–BL-05 so README reflects actual cache and resilience behavior.

---

## Screen coverage matrix

**Assumption:** `04-UI/03-mockup-plan.md` does not exist (solution non-goal). Coverage uses architecture **route ids** instead of mockup screen ids.

| Route id (architecture) | Backlog item(s) | Slice |
| --- | --- | --- |
| `route.health` | BL-01 | F-01 |
| `route.expression` | BL-02, BL-03, BL-04 | F-02, F-03, F-05 |
| `route.chat` | BL-05 | F-04 |

No orphan route ids. When `04-UI/` is authored, re-run step 17 to map mockup screen ids to these items.

## Acceptance traceability (optional, lean)

| Backlog item | Solution draft checklist area / themes |
| --- | --- |
| BL-01 | Ops — service starts; validation before GEO I/O |
| BL-02 | Direct expression — happy path, gene bounds, mapping transparency, multi-gene cells, empty/partial edge |
| BL-03 | Direct expression — cache cold/warm, restart survival, bounded cache |
| BL-04 | Resilience — timeout/retry, bounded concurrency, async I/O |
| BL-05 | Chat agent — happy path, tool invocation, grounded answer, parse failure, stub LLM |
| BL-06 | Documentation — README run, mapping/cache paragraphs |

Formal **SR-…** IDs pending `02-Requirements/02-system-requirements.md` (Step 7).

## Review checklist

- [ ] Six backlog items cover all six feature slices (F-01–F-06)
- [ ] Order respects feature-slice dependency graph (F-01 → F-02 → F-03 → F-04 → F-05 → F-06)
- [ ] Every architecture route id appears in at least one item
- [ ] Tasks name concrete paths from `03-architecture.md` — no vague “implement feature”
- [ ] No scope beyond solution draft (no web UI, DB, auth, SSE, gene lists >5)
- [ ] All summary rows have **Status** `not started`
- [ ] Screen coverage documented for deferred UI (route-id substitute)

## Implementation decisions (2025-06-14)

Pre-implementation interview — locked for Phase 7:

| # | Topic | Decision |
| --- | --- | --- |
| 1 | Repo layout | **Single repo** — `pyproject.toml` + Python package `geo_expression_service/` at repository root |
| 2 | Matrix / annotation parsing | **stdlib `csv` only** — no pandas; document trade-offs in BL-06 README |
| 3 | F-05 (BL-04) in assessment MVP | **Yes** — retries, timeouts, semaphore ship before assessment |
| 4 | Order after cache | **Chat before resilience** — BL-05 then BL-04 after BL-03 |
| 5 | Formal BR/SR (Steps 6–7) | **Defer** — start BL-01 now; author requirements in parallel or post-MVP |

## Assumptions

1. Python package `geo_expression_service/` and `pyproject.toml` at repository root — **confirmed**.
2. No mockup-plan screen ids — route ids satisfy coverage until `04-UI/` exists.
3. Tabular parsing uses **stdlib `csv` only** (no pandas) — **confirmed**; BL-06 README explains trade-offs.
4. Chat MVP is stateless (single-turn per `POST /chat`).
5. BL-04 (F-05) is **in assessment MVP** — **confirmed**; linear order BL-05 → BL-04 after cache.
6. Formal **SR-…** traceability deferred until Steps 6–7 — **Done when** bullets use solution draft acceptance until then.
7. All items default to `not started`; no prior implementation assumed.

## Open questions

1. **04-UI deferral:** No mockup screen ids today; when chat web UI is added, run UI steps 10–15 and extend screen coverage matrix — target slice TBD (likely new F-xx).
2. **SSE streaming:** Remains stretch; BL-05 uses blocking JSON unless scope changes.
3. **Scenarios / glossary:** Author `01-Context/02-scenarios.md` and `01-Context/03-glossary.md` for chat phrasing nuance — optional, non-blocking.
4. **Researcher persona:** Bench scientist vs core-facility analyst — affects chat phrasing defaults only.
