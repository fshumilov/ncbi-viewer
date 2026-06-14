# Stakeholders

## General idea

**GEO Expression Service** is a small Python service for exploring gene expression from [NCBI GEO](https://www.ncbi.nlm.nih.gov/geo/). GEO organizes data as **GSE** (study/series), **GSM** (samples), and **GPL** (measurement platform). Expression matrices are indexed by probe IDs (e.g. `1007_s_at`), not gene symbols — so answering *"what is TP53 expression?"* requires downloading GPL annotation and mapping probes → symbols, then aggregating multiple probes per gene.

The product has two parts: a **FastAPI backend** that, given a GSE and 2–5 gene symbols, returns boxplots of each gene's expression across samples; and a **pydantic-ai chatbot** with at least one tool that calls that logic so users can ask in natural language (*"Show me TP53 and BRCA1 expression in GSE2034"*) and receive a plot plus a grounded text answer — not a hallucinated reply. Two engineering problems dominate: **robust gene mapping** on messy real annotations, and **bounded caching** so repeat requests for the same series/platform/genes are near-instant while first requests may be slow. Built as an assessment deliverable (repo shared in advance); graded on mapping correctness, measurable cache speedup, real tool invocation, and clean async architecture.

| Stakeholder | Type | Top goal | Top pain |
| --- | --- | --- | --- |
| Bioinformatics researcher | Primary user | Get accurate per-gene expression boxplots for a chosen GSE without manual probe mapping or GEO file wrangling | Matrices keyed by probe IDs; inconsistent GPL annotations; long first download; repeat queries still slow without caching |
| Technical assessor / reviewer | Decision-maker | Verify defensible mapping, measurable cache speedup on repeat calls, real tool-calling, async layering, and a README that explains trade-offs | Plausible chat answers with no data fetch; silent loss of unmapped probes; unbounded caches; blocking `requests`; bare exception handling |
| Service developer (candidate) | Implementer | Ship FastAPI + pydantic-ai with `POST /chat` and direct expression access (e.g. `GET /expression`), async GEO I/O, and defensible design under discussion | One gene → many probes; multi-gene annotation cells; varying column names; large slow downloads; choosing cache layers and eviction under time pressure |

## Bioinformatics researcher

- **Type:** Primary user
- **Goals:** Name a GSE and 2–5 gene symbols and receive usable boxplots (PNG/base64 or renderable JSON) plus a short interpretation; trust that values come from fetched GEO data, not model invention; see mapping transparency (e.g. how many probes mapped per gene, not silent total drop).
- **Pains:** Cannot query gene symbols directly against probe-keyed matrices; must locate GPL annotation, parse files with varying columns (`Gene Symbol`, `GENE_SYMBOL`, `SYMBOL`, …) and messy values (multi-gene `TP53 /// WRAP53`, missing/`---`/null); must choose probe aggregation (e.g. mean of log2 values); first GEO/platform download can take minutes; **repeat requests for the same series/genes should not wait again** — unbounded or absent caching wastes time on every visit.

## Technical assessor / reviewer

- **Type:** Decision-maker (grading / assessment scope)
- **Goals:** Confirm probe→symbol mapping is correct and justified (aggregation, multi-gene cells, missing data, surfaced unmapped counts); observe **measurable** speedup on an identical second request with a **bounded** eviction policy (e.g. timing logs or `cached: true/false`); verify chatbot **actually invokes a tool** and grounds its answer in fetched results (stub LLM OK if wiring is real); review API ↔ service ↔ external-client separation, specific exception handling, async network I/O (`httpx.AsyncClient`); optional credit for tests (mapping unit test, cache faster-on-second-call test), bounded concurrency, two-tier cache, resilience patterns — per README and code quality.
- **Pains:** Chat replies that score zero because no tool ran and no GEO data was fetched; caches that grow forever with no eviction; second call as slow as the first; mapping logic tangled in route handlers; README that only lists run commands without explaining mapping and cache trade-offs.

## Service developer (candidate)

- **Type:** Implementer
- **Goals:** Deliver Python 3.11+ stack with FastAPI and pydantic-ai; implement async I/O for all GEO/network work; expose at least two endpoints (`POST /chat`, direct expression e.g. `GET /expression?gse=...&genes=TP53,BRCA1`); return boxplots in a usable form; add bounded caching at sensible layers (raw file, parsed probe→symbol map, per-gene result — including negative cache); document in README how the two core problems were solved and which trade-offs were chosen; share repo link before assessment day.
- **Pains:** Real GPL files are unpredictable; engineering robust mapping and layered bounded cache simultaneously; deciding what to cache and eviction without over-engineering; proving cache benefit via logs or response flags; optional LLM API key may require stub model while keeping real tool-calling path; time pressure to defend concurrency, retries, and architecture choices in design discussion.

## Open questions

- Is the primary researcher persona an academic bench scientist, a bioinformatics core-facility analyst, or a mixed GEO-literate audience?
- Will anyone consume the direct REST endpoint only (no chat), e.g. a future frontend or notebook integration?
- Are there compliance constraints beyond public NCBI GEO data (institutional policies, export controls)?
