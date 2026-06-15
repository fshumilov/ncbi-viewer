# System requirements

Testable requirements for the **GEO Expression Service**. Derived from `02-Requirements/01-business-requirements.md`, `01-Context/01-stakeholders.md`, `01-Context/02-scenarios.md`, and `docs/GEO_EXPRESSION_SERVICE_SPEC.md`.

**Upstream gaps:** `01-Context/03-glossary.md` and `01-Context/04-interview-notes.md` are not yet authored. Terminology follows stakeholders, scenarios, and business requirements.

**Priority scheme:** **Must** = required for assessment pass; **Should** = strongly expected / spec credit; **Could** = optional enhancement.

## Contents

- [SR-01 — Validated expression query contract](#sr-01-validated-expression-query-contract)
- [SR-02 — Combined per-gene boxplot output](#sr-02-combined-per-gene-boxplot-output)
- [SR-03 — Expression values sourced from GEO](#sr-03-expression-values-sourced-from-geo)
- [SR-04 — Natural-language chat endpoint](#sr-04-natural-language-chat-endpoint)
- [SR-05 — Mandatory expression tool invocation](#sr-05-mandatory-expression-tool-invocation)
- [SR-06 — Clarification for incomplete chat prompts](#sr-06-clarification-for-incomplete-chat-prompts)
- [SR-07 — Direct REST expression endpoint](#sr-07-direct-rest-expression-endpoint)
- [SR-08 — Single service-layer expression implementation](#sr-08-single-service-layer-expression-implementation)
- [SR-09 — Multi-probe per-gene aggregation](#sr-09-multi-probe-per-gene-aggregation)
- [SR-10 — Multi-gene annotation cell resolution](#sr-10-multi-gene-annotation-cell-resolution)
- [SR-11 — Annotation column and sentinel handling](#sr-11-annotation-column-and-sentinel-handling)
- [SR-12 — Per-gene and aggregate mapping statistics](#sr-12-per-gene-and-aggregate-mapping-statistics)
- [SR-13 — Explicit handling of zero-map genes](#sr-13-explicit-handling-of-zero-map-genes)
- [SR-14 — Partial mapping plot delivery](#sr-14-partial-mapping-plot-delivery)
- [SR-15 — Async network I/O for GEO access](#sr-15-async-network-io-for-geo-access)
- [SR-16 — Cold-path timeouts, retries, and failure messages](#sr-16-cold-path-timeouts-retries-and-failure-messages)
- [SR-17 — Cold-path cache-miss observability](#sr-17-cold-path-cache-miss-observability)
- [SR-18 — Measurable warm-cache speedup](#sr-18-measurable-warm-cache-speedup)
- [SR-19 — Cache result consistency](#sr-19-cache-result-consistency)
- [SR-20 — Bounded cache with eviction policy](#sr-20-bounded-cache-with-eviction-policy)
- [SR-21 — Negative result caching](#sr-21-negative-result-caching)
- [SR-22 — Bounded concurrent GEO fetches](#sr-22-bounded-concurrent-geo-fetches)
- [SR-23 — Isolated failure domains per request](#sr-23-isolated-failure-domains-per-request)
- [SR-24 — Layered architecture and specific exceptions](#sr-24-layered-architecture-and-specific-exceptions)
- [SR-25 — Runnable repository and operational instructions](#sr-25-runnable-repository-and-operational-instructions)
- [SR-26 — README design narrative for mapping and caching](#sr-26-readme-design-narrative-for-mapping-and-caching)
- [SR-27 — Required technology stack](#sr-27-required-technology-stack)
- [SR-28 — Persistent disk cache tier](#sr-28-persistent-disk-cache-tier)
- [SR-29 — Automated mapping unit test](#sr-29-automated-mapping-unit-test)
- [SR-30 — Automated cache speedup test](#sr-30-automated-cache-speedup-test)
- [SR-31 — Streaming chat responses](#sr-31-streaming-chat-responses)
- [Coverage summary](#coverage-summary)
- [Revision log](#revision-log)

---

## SR-01 — Validated expression query contract

- **Statement:** The system shall accept expression requests only when the caller supplies a well-formed **GSE** accession and **2–5 unique gene symbols**, rejecting invalid input before any GEO download begins.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-13, BR-06
- **Priority:** Must
- **Acceptance:**
  - Given a request with fewer than 2 or more than 5 gene symbols, when the expression or chat path is invoked, then the system returns a clear validation error without contacting NCBI GEO.
  - Given a malformed or empty GSE identifier, when validated, then the system returns a specific rejection message—not a silent empty plot.
  - Given gene symbols that differ only by case (e.g. `tp53` vs `TP53`), when normalized, then repeat requests resolve to the same cache key for reuse.
- **Assumptions:** Gene discovery, keyword series search, and lists larger than five genes are out of scope for v1.

---

## SR-02 — Combined per-gene boxplot output

- **Statement:** The system shall return **one combined boxplot per request** covering all requested genes that have mappable expression data, in a form consumable by a human reviewer or API client (PNG as base64 or file, or structured JSON a frontend can render).
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-01
- **Priority:** Must
- **Acceptance:**
  - Given a valid GSE and 2–5 genes with at least partial mappable data, when expression is computed, then the response includes a single plot artifact representing per-gene expression distributions across the study's samples.
  - Given the plot payload, when inspected by a reviewer or client, then it is renderable without additional proprietary tooling.
  - Given multiple genes in one request, when plotted, then each mapped gene is distinguishable in the combined visualization (e.g. grouped boxplots per gene).

---

## SR-03 — Expression values sourced from GEO

- **Statement:** The system shall compute expression values exclusively from **downloaded NCBI GEO** series matrices and platform annotations for the requested GSE—not from model-generated or placeholder numbers.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-01, BR-02
- **Priority:** Must
- **Acceptance:**
  - Given a successful expression response, when the underlying GEO files are available, then per-sample values trace to probe rows in the series matrix after probe-to-gene mapping.
  - Given the chat path, when a plot is returned, then the values shown could not have been produced without fetching GEO data for that series.
  - Given a failed GEO download or parse, when no matrix data is available, then the system does not fabricate expression values to fill gaps.

---

## SR-04 — Natural-language chat endpoint

- **Statement:** The system shall expose a **`POST /chat`** endpoint that accepts a natural-language user message and orchestrates a pydantic-ai agent capable of resolving a GSE accession and 2–5 gene symbols from the prompt.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-02
- **Priority:** Must
- **Acceptance:**
  - Given a prompt such as *"Show me TP53 and BRCA1 expression in GSE2034"*, when submitted to `POST /chat`, then the agent extracts or resolves `GSE2034` and genes `TP53`, `BRCA1` within the allowed contract.
  - Given a valid chat request, when processing completes, then the response includes both a plot artifact and short narrative text.
  - Given no LLM API key is configured, when the service runs with a stub model, then the chat endpoint remains callable and the tool-calling path still executes.

---

## SR-05 — Mandatory expression tool invocation

- **Statement:** The system shall require the chat agent to **invoke an expression lookup tool** that calls the same backend logic as the direct REST path; a final reply without a successful tool call for a data-bearing prompt is unacceptable.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-02, BR-10
- **Priority:** Must
- **Acceptance:**
  - Given a chat prompt naming a valid GSE and genes, when the response is produced, then logs or traces show the expression tool was invoked before the final answer.
  - Given a tool result, when the agent composes its reply, then the narrative reflects the fetched plot and mapping metadata—not only pre-trained knowledge.
  - Given a reviewer inspects a successful chat exchange, when they check observability output, then tool invocation and result injection are demonstrable without specialized GEO expertise.

---

## SR-06 — Clarification for incomplete chat prompts

- **Statement:** The system shall request **clarification** when a chat message does not contain a recognizable GSE accession or a gene list within the 2–5 symbol contract, rather than returning a fabricated plot or invented expression summary.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-02
- **Priority:** Must
- **Acceptance:**
  - Given a prompt with no GSE identifier, when processed, then the response asks the user for a series accession and does not return a plot based on guessed data.
  - Given a prompt with zero or one gene symbol, when processed, then the response explains the 2–5 gene requirement or asks for additional symbols.
  - Given an ambiguous prompt, when the agent cannot resolve inputs confidently, then the user receives a clarification message—not a plausible but ungrounded answer.

---

## SR-07 — Direct REST expression endpoint

- **Statement:** The system shall expose a **direct expression endpoint** (e.g. `GET /expression?gse=...&genes=TP53,BRCA1`) that returns boxplots and mapping metadata **without** LLM involvement.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-03
- **Priority:** Must
- **Acceptance:**
  - Given valid query parameters for GSE and comma-separated genes, when `GET /expression` is called, then the response includes the plot payload and mapping statistics.
  - Given the same GSE and genes as a chat-driven request, when both paths are exercised, then underlying expression outcomes are equivalent.
  - Given no LLM API key, when a reviewer calls the direct endpoint, then full expression behavior is verifiable independently of chat.

---

## SR-08 — Single service-layer expression implementation

- **Statement:** The system shall implement probe download, annotation parsing, probe-to-gene mapping, aggregation, and boxplot generation in **one shared service layer** invoked by both the REST endpoint and the chat tool—no duplicated mapping logic in route handlers or agent code.
- **Stakeholder:** Service developer (candidate) · **Maps to:** BR-03, BR-04
- **Priority:** Must
- **Acceptance:**
  - Given the codebase structure, when reviewed, then expression business logic lives outside FastAPI route handlers and outside pydantic-ai prompt strings.
  - Given a change to aggregation policy, when applied, then both REST and chat paths reflect the change through the same module or service class.
  - Given an assessor traces a chat tool call, when followed into the service layer, then it reaches the same functions used by `GET /expression`.

---

## SR-09 — Multi-probe per-gene aggregation

- **Statement:** The system shall aggregate **multiple probes mapping to the same gene** using a documented, defensible rule (e.g. mean of log2-transformed expression values) and apply it consistently for every gene in a request.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-04, BR-11
- **Priority:** Must
- **Acceptance:**
  - Given a gene with N>1 mapped probes, when per-sample expression is computed, then the system produces one value per sample derived from all mapped probes per the documented rule.
  - Given the README or API metadata, when read by a reviewer, then the aggregation rule and rationale are stated explicitly.
  - Given the same inputs on repeat calls, when aggregation runs, then per-gene values are identical across cold and warm paths.

---

## SR-10 — Multi-gene annotation cell resolution

- **Statement:** The system shall resolve GPL annotation cells containing **multiple gene symbols** (e.g. `TP53 /// WRAP53`) by matching the requested symbol when present, without treating the entire cell as an unmatchable opaque string.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-04
- **Priority:** Must
- **Acceptance:**
  - Given an annotation cell `TP53 /// WRAP53` and a request for `TP53`, when mapping runs, then probes in that cell contribute to `TP53` aggregation.
  - Given an annotation cell with multiple symbols and a request for a symbol not in the cell, when mapping runs, then that probe does not map to the requested gene.
  - Given mixed single- and multi-gene cells in one platform file, when mapping completes, then both cell types are handled without aborting the full matrix.

---

## SR-11 — Annotation column and sentinel handling

- **Statement:** The system shall parse platform annotation files despite **varying gene-symbol column names** (e.g. `Gene Symbol`, `GENE_SYMBOL`, `SYMBOL`) and **missing or sentinel values** (null, empty, `---`), without crashing or discarding the entire expression matrix.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-04
- **Priority:** Must
- **Acceptance:**
  - Given a GPL file whose symbol column uses a supported variant name, when parsed, then probes with valid symbols are mapped without manual column renaming.
  - Given rows with null, empty, or `---` symbol values, when parsed, then those probes are skipped and counted as unmapped—not treated as valid gene symbols.
  - Given a partially messy annotation file with some valid rows, when mapping runs, then valid probes still contribute to results and the response reports how many probes were unmapped in aggregate.

---

## SR-12 — Per-gene and aggregate mapping statistics

- **Statement:** The system shall include **mapping coverage metadata** in every expression response: per-gene probe counts used, and aggregate visibility into unmapped or skipped probes.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-05
- **Priority:** Must
- **Acceptance:**
  - Given a successful expression response, when inspected, then each requested gene lists how many probes mapped (or zero with a stated reason).
  - Given probes that could not map to any requested gene, when mapping completes, then the response reports an aggregate unmapped or skipped probe count.
  - Given a reviewer compares mapping stats to raw GPL content, when spot-checking, then reported counts are consistent with implemented mapping rules.

---

## SR-13 — Explicit handling of zero-map genes

- **Statement:** The system shall report **each requested gene with zero mapped probes** explicitly in the outcome—never silently omitting a gene the user asked for.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-05, BR-09
- **Priority:** Must
- **Acceptance:**
  - Given a request for genes A and B where only A maps, when the response is returned, then gene B appears with zero probes mapped and a clear reason (e.g. no matching annotation).
  - Given all requested genes map to zero probes, when mapping completes, then the response states that outcome with per-gene detail—not an empty 200 with no explanation.
  - Given zero-map genes, when the plot is generated, then mapped genes may still appear in the visualization per SR-14; unmappable genes are listed in metadata regardless.

---

## SR-14 — Partial mapping plot delivery

- **Statement:** The system shall deliver a **plot for successfully mapped genes** when at least one requested gene has mappable probes, even if other requested genes map to zero probes.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-05, BR-09
- **Priority:** Must
- **Acceptance:**
  - Given a request where 2 of 3 genes map, when expression completes, then the plot includes the two mapped genes and metadata explains the third gene's zero-map status.
  - Given a request where no genes map, when expression completes, then no fabricated plot is returned; the response is a structured outcome with mapping stats and an explicit empty or not-available indication.
- **Assumptions:** Resolves BR-05 open question—partial success is preferred over whole-request failure when some genes map.

---

## SR-15 — Async network I/O for GEO access

- **Statement:** The system shall perform **all GEO and platform annotation downloads** using async I/O (`httpx.AsyncClient` or equivalent), not blocking synchronous HTTP clients such as `requests`.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-06, BR-12
- **Priority:** Must
- **Acceptance:**
  - Given codebase review, when GEO client modules are inspected, then no blocking HTTP library is used on the request hot path.
  - Given concurrent expression requests, when downloads overlap, then the event loop is not blocked waiting on a single synchronous socket read.
  - Given a large matrix download in progress, when another unrelated request arrives, then the second request can progress without waiting for the first download's blocking I/O to finish.

---

## SR-16 — Cold-path timeouts, retries, and failure messages

- **Statement:** The system shall apply **timeouts and bounded retries with backoff** to GEO downloads and return **understandable error outcomes** for network failures, missing series, and parse errors—never indefinite hangs or bare generic crashes.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-06, BR-12
- **Priority:** Must
- **Acceptance:**
  - Given an unreachable or slow NCBI endpoint, when retries are exhausted within the configured budget, then the caller receives a specific error message indicating fetch failure—not an unhandled exception stack trace as the only outcome.
  - Given a non-existent GSE, when resolved, then the system fails with feedback that the series could not be found or loaded—not a blank plot.
  - Given a corrupt or unparseable GEO file, when parsing fails, then the error identifies parse failure and does not return invented expression data.
- **Assumptions:** Timeout values may scale with expected file size; exact thresholds are implementation choices documented in README.

---

## SR-17 — Cold-path cache-miss observability

- **Statement:** The system shall make **first-time (cache-miss) requests observable** via response metadata (e.g. `cached: false`), structured logs, or equivalent timing fields so users and assessors can distinguish cold-path latency from warm-path reuse.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-06, BR-07
- **Priority:** Must
- **Acceptance:**
  - Given a first request for a GSE/gene combination with no prior cache entry, when the response is returned, then metadata or logs indicate a cache miss and record request duration.
  - Given an assessor runs two identical requests, when comparing outcomes, then the first is clearly labeled or logged as uncached relative to the second.
  - Given a cold-path request that succeeds, when duration is logged, then the recorded time reflects GEO download and processing—not only client round-trip.

---

## SR-18 — Measurable warm-cache speedup

- **Statement:** The system shall complete an **identical repeat request** (same GSE, same normalized genes, same platform context) **measurably faster** than the first call, with order-of-magnitude reduction verifiable via timing logs or `cached: true` (or equivalent) in the response.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-07
- **Priority:** Must
- **Acceptance:**
  - Given two back-to-back identical valid expression requests, when the second completes, then its server-side duration is substantially lower than the first (e.g. at least 10× faster for cache-eligible work, or near-instant relative to GEO download time).
  - Given the second response, when metadata is inspected, then a cache-hit indicator or equivalent proof is present.
  - Given an assessor without specialized tooling, when they repeat a curl or API call, then speedup is observable from logs or response flags alone.

---

## SR-19 — Cache result consistency

- **Statement:** The system shall return **equivalent plot data and mapping metadata** on cache hits as on the original cold-path computation for the same inputs.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-07
- **Priority:** Must
- **Acceptance:**
  - Given two identical requests where the second is a cache hit, when plot payloads and mapping stats are compared, then they match the first response (modulo non-functional fields such as `cached` or timestamps).
  - Given cache eviction and a subsequent cold miss for the same inputs, when recomputed, then results remain consistent with a fresh GEO fetch absent upstream GEO data changes.

---

## SR-20 — Bounded cache with eviction policy

- **Statement:** The system shall enforce a **bounded cache** with a documented **eviction policy** (e.g. LRU by entry count or total size) so memory and/or disk use cannot grow without limit under sustained distinct queries.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-08
- **Priority:** Must
- **Acceptance:**
  - Given cache configuration, when reviewed, then a maximum capacity (entries, bytes, or equivalent) is defined and enforced.
  - Given capacity is exceeded, when new entries are stored, then older entries are evicted per the stated policy—not retained indefinitely.
  - Given sustained requests for many distinct GSE/gene combinations beyond capacity, when the service runs, then it continues to respond correctly without out-of-memory failure from unbounded cache growth.

---

## SR-21 — Negative result caching

- **Statement:** The system shall **cache negative mapping outcomes** (e.g. platform with no usable symbols, zero-map gene set for a known GPL) so repeat identical requests do not re-download and re-parse the same dead end.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-09, BR-07
- **Priority:** Must
- **Acceptance:**
  - Given a first request that yields zero or partial unmappable results for a platform, when an identical second request arrives, then it completes quickly from cache with the same structured negative outcome.
  - Given a cached negative result, when returned, then mapping stats and per-gene failure reasons match the first request.
  - Given negative cache entries, when eviction runs, then they follow the same bounded policy as positive entries.

---

## SR-22 — Bounded concurrent GEO fetches

- **Statement:** The system shall limit **parallel GEO and annotation downloads** with bounded concurrency (e.g. a semaphore), avoiding unbounded fan-out when multiple genes, platforms, or requests overlap.
- **Stakeholder:** Service developer (candidate) · **Maps to:** BR-12
- **Priority:** Should
- **Acceptance:**
  - Given multiple simultaneous expression requests, when external fetches are scheduled, then concurrent NCBI connections do not exceed a configured maximum.
  - Given parallel work inside a single request (e.g. matrix and annotation), when downloads are parallelized, then concurrency remains within the same bound.
  - Given the README or configuration, when reviewed, then the concurrency limit is documented or configurable.

---

## SR-23 — Isolated failure domains per request

- **Statement:** The system shall **isolate failures** so one request's failed GEO download or parse error does not prevent unrelated concurrent requests from completing successfully.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-12
- **Priority:** Must
- **Acceptance:**
  - Given concurrent requests for different GSE accessions, when one download fails after retries, then other in-flight requests still return their own success or failure outcomes.
  - Given a shared cache, when one request writes an entry, then concurrent readers and writers do not corrupt cache state or return mixed payloads.
  - Given per-request error handling, when a failure occurs, then logs identify the failing request context (e.g. GSE, request id) without masking unrelated successes.

---

## SR-24 — Layered architecture and specific exceptions

- **Statement:** The system shall separate **API routes**, **expression service logic**, and **GEO external-client adapters**, using **specific exception types** (not bare `except:` or silent swallowing) at integration boundaries.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-12, BR-10
- **Priority:** Must
- **Acceptance:**
  - Given codebase review, when modules are mapped, then HTTP handlers, domain service, and NCBI client code reside in distinct layers with one-directional dependencies.
  - Given a GEO timeout, parse error, or validation error, when caught, then handlers translate known exception types to appropriate HTTP status and messages.
  - Given an unexpected internal error, when it occurs, then it is logged with context and surfaced as a controlled error response—not an unhandled crash of the process for a single bad request.

---

## SR-25 — Runnable repository and operational instructions

- **Statement:** The system shall be delivered as a **runnable repository** with a README that explains how to install dependencies, configure optional LLM keys, start the service, and exercise both `POST /chat` and the direct expression endpoint; the repository link shall be shared **at least one day before assessment**.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-10
- **Priority:** Must
- **Acceptance:**
  - Given a clean environment with Python 3.11+, when a reviewer follows README steps, then the FastAPI service starts and responds to health or expression requests.
  - Given the assessment timeline, when the repo is submitted, then the link was available ≥1 day before assessment day.
  - Given optional LLM configuration, when absent, then the reviewer can still validate expression logic and tool wiring per SR-05 and SR-07.

---

## SR-26 — README design narrative for mapping and caching

- **Statement:** The system README shall include **distinct sections** explaining how the **gene-mapping problem** and the **reuse/caching problem** were solved, including stated **trade-offs** for aggregation, multi-gene handling, cache layers, and eviction.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-11
- **Priority:** Must
- **Acceptance:**
  - Given README review, when mapping section is read, then probe aggregation, multi-gene cells, and column-variant handling are explained in prose aligned with implemented behavior.
  - Given README review, when caching section is read, then cached layers, eviction policy, negative caching, and cold vs warm behavior are explained with trade-offs—not only a list of start commands.
  - Given a design discussion, when the implementer is challenged on a documented choice, then the README rationale matches observable system behavior.

---

## SR-27 — Required technology stack

- **Statement:** The system shall be implemented in **Python 3.11+** using **FastAPI** for HTTP APIs and **pydantic-ai** for the chat agent, consistent with the assessment specification.
- **Stakeholder:** Service developer (candidate) · **Maps to:** BR-10
- **Priority:** Must
- **Acceptance:**
  - Given dependency manifests or project metadata, when inspected, then Python version requirement is ≥3.11 and FastAPI and pydantic-ai are declared dependencies.
  - Given runtime inspection, when the service runs, then it is served by the FastAPI application with pydantic-ai orchestrating chat tool calls.

---

## SR-28 — Persistent disk cache tier

- **Statement:** The system should implement a **two-tier cache** with an in-memory LRU fronting a **persistent on-disk layer** so warm results can survive service restarts, subject to the same bounded eviction rules.
- **Stakeholder:** Service developer (candidate) · **Maps to:** BR-07, BR-08
- **Priority:** Should
- **Acceptance:**
  - Given a successful cold-path request, when the service restarts before eviction, then an identical request is served from disk cache without full GEO re-download.
  - Given disk cache limits, when exceeded, then eviction applies to on-disk entries predictably (e.g. LRU aligned with memory tier policy).
- **Assumptions:** In-memory LRU alone satisfies Must-level reuse (SR-18–SR-20); persistent tier is spec-recommended credit. No institutional retention policy is defined upstream—local retention follows configured cache bounds.

---

## SR-29 — Automated mapping unit test

- **Statement:** The system should include an **automated unit test** for probe-to-gene mapping logic covering multi-probe aggregation, multi-gene cells, column variants, and sentinel values—without requiring live NCBI access.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-04, BR-10
- **Priority:** Should
- **Acceptance:**
  - Given a test fixture resembling messy GPL annotation rows, when the mapping test runs, then expected probes map to requested symbols per SR-09–SR-11.
  - Given CI or local `pytest` (or equivalent), when tests execute, then the mapping test passes without network calls.

---

## SR-30 — Automated cache speedup test

- **Statement:** The system should include an **automated test** that proves the second identical expression request completes faster than the first (or reports a cache hit), using an in-memory or mocked GEO client where live NCBI is impractical.
- **Stakeholder:** Technical assessor / reviewer · **Maps to:** BR-07, BR-10
- **Priority:** Should
- **Acceptance:**
  - Given two sequential calls with identical inputs in the test harness, when timed or inspected for cache metadata, then the second call demonstrates measurably lower latency or `cached: true`.
  - Given the test suite, when run offline, then the cache test does not depend on live GEO availability unless explicitly marked as integration.

---

## SR-31 — Streaming chat responses

- **Statement:** The system could stream **`POST /chat` responses** via Server-Sent Events (SSE) rather than returning one blocking JSON payload after full agent completion.
- **Stakeholder:** Bioinformatics researcher · **Maps to:** BR-02
- **Priority:** Could
- **Acceptance:**
  - Given a chat client that accepts `text/event-stream`, when a long-running expression tool executes, then partial agent output or status events arrive before the final plot is ready.
  - Given streaming is enabled, when the tool completes, then the final event includes or references the plot artifact and grounded summary.
- **Assumptions:** Single complete JSON response satisfies Must-level BR-02; streaming is optional spec credit per scenario S-01 open question.

---

## Coverage summary

| Scenario | Primary SR ids |
| --- | --- |
| S-01 Natural-language chat | SR-04, SR-05, SR-06, SR-09–SR-14, SR-31 |
| S-02 Direct REST expression | SR-07, SR-08, SR-09–SR-14 |
| S-03 Cold path / first request | SR-01, SR-11, SR-15–SR-17, SR-24 |
| S-04 Warm cache / repeat request | SR-18–SR-20, SR-28, SR-30 |
| S-05 Negative / unmappable platform | SR-13, SR-14, SR-21 |
| S-06 Assessor validation | SR-05, SR-25–SR-27, SR-29, SR-30 |
| S-07 Concurrent load | SR-15, SR-16, SR-22, SR-23, SR-24 |

| BR | Mapped SR ids |
| --- | --- |
| BR-01 | SR-02, SR-03 |
| BR-02 | SR-03–SR-06, SR-31 |
| BR-03 | SR-07, SR-08 |
| BR-04 | SR-08–SR-11, SR-29 |
| BR-05 | SR-12–SR-14 |
| BR-06 | SR-01, SR-15–SR-17 |
| BR-07 | SR-17–SR-19, SR-28, SR-30 |
| BR-08 | SR-20, SR-28 |
| BR-09 | SR-13, SR-14, SR-21 |
| BR-10 | SR-05, SR-24, SR-25, SR-27, SR-29, SR-30 |
| BR-11 | SR-09, SR-26 |
| BR-12 | SR-15, SR-16, SR-22–SR-24 |
| BR-13 | SR-01 |

## Revision log

- 2026-06-15 — Initial system requirements from business requirements, stakeholders, scenarios, and GEO expression service task spec (glossary and interview notes pending).
