# GEO Expression Service — описание задания

> You have to create a repo and share the link in advance at least one day before the assessment day.

---

## Background

NCBI GEO is a public archive of gene expression experiments. Three entities matter for this task:

- **GSE** — a series (one study), containing many samples.
- **GSM** — an individual sample with measured expression values.
- **GPL** — the platform (e.g. a microarray) the samples were measured on.

An expression matrix is indexed by probe IDs (e.g. `1007_s_at`), not gene symbols. To answer "what is the expression of TP53?" you must download the platform's annotation and translate probes → gene symbols. One gene typically maps to several probes, and the annotation files are messy.

---

## What to build

A small service with two parts:

1. A **FastAPI backend** that, given a GEO series and a short list of gene symbols (2–5 genes), downloads the expression matrix, maps probes to gene symbols, and computes a boxplot of each gene's expression across samples.
2. A **pydantic-ai chatbot** with at least one tool that calls the backend logic above. A user should be able to type something like *"Show me TP53 and BRCA1 expression in GSE2034"* and get a plot plus a short text answer. The agent must actually call a tool — a reply the LLM could have produced on its own, with no data fetched, scores zero.

---

## The two problems we are actually evaluating

### 1. The gene-mapping problem

The expression matrix is keyed by probe IDs; the platform annotation maps probes → symbols. Make this robust to the real mess:

- One gene → many probes. Decide and justify an aggregation (e.g. mean of log2 values).
- Annotation cells contain multi-gene values like `TP53 /// WRAP53` — pick sensibly.
- Column names vary (`Gene Symbol`, `GENE_SYMBOL`, `SYMBOL`, …) and values can be missing / null / `---`.
- Some probes never map. Don't silently drop everything — surface how many mapped.

### 2. The app-reuse problem (don't make users wait — especially on repeats)

GEO downloads are slow and large; platform annotations in particular. But the same gene / series / platform gets requested over and over. The first request may be slow; a second request for the same thing must be near-instant.

- Add caching / memoization so repeated work is not repeated.
- Think about what to cache and at which layer: the raw downloaded file, the parsed probe→symbol map, the final per-gene result?
- Bound it. An unbounded dict that grows forever is not a cache. Show an eviction policy.
- Make the speedup measurable — e.g. log timing, or return a `cached: true/false` flag, so a reviewer can see the second call is fast.

---

## Minimum requirements

- Python 3.11+, FastAPI, pydantic-ai.
- Async I/O for all network calls (`httpx.AsyncClient`, not blocking `requests`).
- At least two endpoints, e.g. `POST /chat` (the agent) and a direct `GET /expression?gse=...&genes=TP53,BRCA1` (the underlying logic).
- The boxplot returned in a usable form — a PNG (base64 or file) or structured JSON a frontend could render. One plot is enough.
- A short README: how to run it, and a paragraph each on how you solved the two problems above and the trade-offs you made.
- If you have no LLM API key, you may stub the model — but the tool-calling wiring must be real (the tool must be invoked and its result fed back to the agent).

---

## Pick whatever you'd defend in a design discussion

- **Concurrency:** fetch multiple genes / platforms in parallel with bounded concurrency (e.g. a semaphore), not an unbounded fan-out.
- **Two-tier cache:** in-memory LRU in front of a persistent on-disk layer that survives restarts; cache negative results too (a platform that yields no symbols shouldn't be re-downloaded every time).
- **Resilience:** retries with backoff, timeouts sized to file size, resumable / partial downloads.
- **Streaming:** stream the chat response (SSE) instead of one blocking reply.
- **Tests:** a unit test for the mapping logic and a test proving the cache returns the same answer faster on the second call.

---

## What we look for when grading

- The mapping is correct and defensible (aggregation, multi-gene cells, missing data).
- The cache actually works — a measurable speedup on the repeat call, and it's bounded.
- The chatbot calls a tool and grounds its answer in fetched data.
- Clean async code, specific (not bare) exception handling, clear separation of API ↔ service ↔ external-client layers.
- A README that explains decisions, not just how to run.

---

**Основная ссылка на сайт:** https://www.ncbi.nlm.nih.gov/geo/
