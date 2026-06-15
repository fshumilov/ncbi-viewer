# Business scenarios

Concrete situations the **GEO Expression Service** must support. Each scenario maps actors to stakeholders in `01-Context/01-stakeholders.md` and reflects the assessment scope in `docs/GEO_EXPRESSION_SERVICE_SPEC.md`.

## Contents

- [S-01 — Natural-language expression query via chat](#s-01-natural-language-expression-query-via-chat)
- [S-02 — Direct REST expression lookup (no chat)](#s-02-direct-rest-expression-lookup-no-chat)
- [S-03 — First request on a new GSE / platform (cold path)](#s-03-first-request-on-a-new-gse-platform-cold-path)
- [S-04 — Repeat request for the same GSE and genes (warm cache)](#s-04-repeat-request-for-the-same-gse-and-genes-warm-cache)
- [S-05 — Platform with no usable gene symbols (negative cache)](#s-05-platform-with-no-usable-gene-symbols-negative-cache)
- [S-06 — Assessor validates tool-calling and architecture](#s-06-assessor-validates-tool-calling-and-architecture)
- [S-07 — Concurrent requests under load (bounded parallelism)](#s-07-concurrent-requests-under-load-bounded-parallelism)
- [Assumptions](#assumptions)
- [Open questions](#open-questions)
- [Revision log](#revision-log)

---

## S-01 — Natural-language expression query via chat

- **Actors:** Bioinformatics researcher (primary user); pydantic-ai chat agent; FastAPI backend; NCBI GEO (external).
- **Context:** Researcher at a laptop with internet access, reviewing a published breast-cancer microarray study. Session length: a few minutes per question. No clinical supervision required — exploratory analysis on public GEO data.
- **Trigger:** Researcher types *"Show me TP53 and BRCA1 expression in GSE2034"* in the chat UI or `POST /chat` client.
- **Flow:** Agent parses GSE and gene list (2–5 symbols), invokes the expression tool, backend resolves the series’ GPL, downloads expression matrix and platform annotation asynchronously, maps probes → symbols with chosen aggregation, builds one combined boxplot (PNG/base64 or renderable JSON), returns plot plus short grounded summary. Response may stream (SSE) if implemented.
- **Success:** Researcher receives a plot and text that clearly reflect fetched GEO data; answer cites or implies real sample-level values, not model invention.
- **Failure / pain:** Without the product, researcher manually downloads SOFT/Matrix files, finds GPL annotation, handles probe IDs and messy symbol columns, and plots in R/Python — or accepts a chat reply with no data fetch (scores zero on assessment).

---

## S-02 — Direct REST expression lookup (no chat)

- **Actors:** Bioinformatics researcher or integrator (notebook, script, future frontend); FastAPI backend; NCBI GEO.
- **Context:** Same connectivity as S-01; caller prefers programmatic access (`GET /expression?gse=GSE2034&genes=TP53,BRCA1`) over natural language.
- **Trigger:** HTTP GET with valid GSE id and comma-separated gene symbols (2–5 genes).
- **Flow:** Request hits expression endpoint directly; service layer performs download, mapping, aggregation, and boxplot generation without LLM involvement; response includes plot payload and mapping metadata (e.g. probes mapped per gene).
- **Success:** Identical underlying logic and data quality as chat path; usable for automation and reviewer smoke tests without an LLM key.
- **Failure / pain:** Duplicated or divergent logic between chat tool and REST route; blocking I/O causing timeouts on large series.

---

## S-03 — First request on a new GSE / platform (cold path)

- **Actors:** Bioinformatics researcher; service developer’s caching layer; NCBI GEO.
- **Context:** No prior cache entry for this GSE, GPL, or gene set. GEO matrix and GPL annotation files may be large; first response may take tens of seconds to minutes.
- **Trigger:** First-ever (or post-eviction) request for a given series and genes.
- **Flow:** Async client downloads series matrix and platform annotation with timeouts/retries; parser detects annotation column variants (`Gene Symbol`, `GENE_SYMBOL`, `SYMBOL`, …), splits multi-gene cells (`TP53 /// WRAP53`), skips missing/`---`/null sensibly; aggregates multiple probes per gene (e.g. mean of log2); surfaces how many probes mapped vs unmapped; stores results in bounded cache layers; logs duration and/or returns `cached: false`.
- **Success:** Researcher gets correct boxplots and transparency on mapping coverage; accepts slower first load as expected for cold GEO fetch.
- **Failure / pain:** Silent drop of all probes when annotation is messy; unbounded wait with no timeout; user cannot tell whether slowness is network or mapping failure.

---

## S-04 — Repeat request for the same GSE and genes (warm cache)

- **Actors:** Bioinformatics researcher; technical assessor (observing); in-memory and/or on-disk cache.
- **Context:** Same session or a later visit after service restart (if persistent cache tier exists). Reviewer may call the same endpoint twice to grade speedup.
- **Trigger:** Identical or equivalent request shortly after S-03 (same GSE, same genes, same GPL).
- **Flow:** Service hits cache at appropriate layer (raw file, parsed probe→symbol map, and/or per-gene result); skips or minimizes re-download; returns same plot/data with `cached: true` or clearly faster timing in logs; LRU (or similar) eviction prevents unbounded growth.
- **Success:** Second response is near-instant and measurably faster than the first; assessor can verify via flag or logs.
- **Failure / pain:** Every repeat still re-downloads GPL annotation; cache dict grows without eviction; second call as slow as the first — fails core assessment criterion.

---

## S-05 — Platform with no usable gene symbols (negative cache)

- **Actors:** Bioinformatics researcher; service; NCBI GEO.
- **Context:** GPL annotation exists but yields no mappable symbols for requested genes (wrong platform, retired array, or empty symbol column).
- **Trigger:** Request for genes that do not map on the series’ platform, or platform file that parses to zero valid symbols.
- **Flow:** Mapping pipeline completes with zero or partial hits; response reports unmapped counts and which genes failed; negative result cached so the same bad platform is not re-downloaded on every request.
- **Success:** Researcher understands why plot is empty or partial; repeat calls are fast from negative cache.
- **Failure / pain:** Repeated expensive downloads for “known bad” platforms; generic 500 error with no mapping stats.

---

## S-06 — Assessor validates tool-calling and architecture

- **Actors:** Technical assessor / reviewer; chat endpoint; expression tool; README and test suite.
- **Context:** Assessment day or pre-submission review; repo shared in advance. Reviewer may use stub LLM if no API key, but tool wiring must be real.
- **Trigger:** Reviewer sends chat prompt, inspects logs/traces for tool invocation, runs direct `GET /expression`, executes unit test for mapping and cache speed test, reads README trade-offs.
- **Flow:** Reviewer confirms tool was called and result fed back to agent; checks async `httpx` usage, API ↔ service ↔ client layering, specific exceptions; verifies mapping tests and second-call-faster cache test if present.
- **Success:** Evidence of grounded answers, defensible mapping choices documented, measurable cache behavior, clean separation of concerns.
- **Failure / pain:** Plausible LLM answer with no GEO fetch; mapping buried in route handlers; README only lists `uvicorn` command with no mapping/cache narrative.

---

## S-07 — Concurrent requests under load (bounded parallelism)

- **Actors:** Multiple researchers or automated clients; service developer’s concurrency controls; NCBI GEO.
- **Context:** Several users or parallel gene/platform fetches during a demo; NCBI rate limits and large files make unbounded fan-out risky.
- **Trigger:** Multiple simultaneous expression or chat requests for different GSEs or overlapping GPL downloads.
- **Flow:** Service uses bounded concurrency (e.g. semaphore) for parallel GEO fetches; shares cache safely; failed downloads retry with backoff within timeout budget.
- **Success:** Throughput improves vs strict serial without overwhelming network or GEO; failures are isolated and logged per request.
- **Failure / pain:** Unbounded parallel downloads cause timeouts and throttling; one slow GPL blocks all workers; race conditions corrupt cache entries.

---

## Assumptions

- Primary user is GEO-literate enough to know a **GSE** accession and **gene symbols** (2–5 per request); no need to discover series by keyword in v1.
- All data comes from **public NCBI GEO**; no institutional auth, PHI, or export-control constraints beyond normal internet access to NCBI.
- Chat and REST share one **service-layer** implementation for expression logic (no duplicate mapping code paths).
- Boxplot output in **one combined plot** per request is sufficient; separate PNG per gene is optional, not required.
- Assessment environment: Python 3.11+, local or container run; reviewer has network access to GEO.
- Stub LLM is acceptable when no API key, provided **tool invocation and result injection** are real (per spec).

## Open questions

- **S-01 / S-02:** Will a first-party UI exist, or is chat consumed only via API clients (curl, Postman, notebook)?
- **S-01:** Is streaming (SSE) required for pass, or optional credit only?
- **S-03 / S-05:** Should partial mapping (some genes mapped, others not) still produce a plot for mapped genes, or fail the whole request?
- **S-04:** Must persistent on-disk cache survive restarts for full credit, or is in-memory LRU alone acceptable if eviction and speedup are demonstrated?
- **S-07:** Expected concurrency level for assessment (single reviewer vs small team demo)?
- **Regulations:** Any institutional policy on caching third-party GEO files locally (retention period)?

## Revision log

- 2026-06-15 — Initial scenarios from stakeholders, GEO expression service spec, and assessment grading criteria (no glossary or interview notes yet).
