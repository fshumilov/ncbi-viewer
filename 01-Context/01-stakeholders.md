# Stakeholders

## General idea

**GEO Expression Service** is a small Python service for exploring gene expression from [NCBI GEO](https://www.ncbi.nlm.nih.gov/geo/). A researcher names a GEO series (GSE) and a few gene symbols (e.g. TP53, BRCA1); the system downloads the expression matrix, maps platform probe IDs to gene symbols via GPL annotation, aggregates probe-level values per gene, and returns boxplots across samples. A pydantic-ai chatbot wraps the same logic so users can ask in natural language (*"Show me TP53 and BRCA1 expression in GSE2034"*) and receive a plot plus a grounded text answer — not a hallucinated reply. The product must handle real-world annotation mess (multi-gene cells, varying column names, missing values) and make repeat queries near-instant through bounded caching.

| Stakeholder | Type | Top goal | Top pain |
| --- | --- | --- | --- |
| Bioinformatics researcher | Primary user | Get accurate per-gene expression plots for a GSE without manual probe mapping or GEO file wrangling | Expression matrices use probe IDs, not gene symbols; platform annotations are inconsistent; first GEO download is slow |
| Technical assessor / reviewer | Decision-maker | Verify defensible gene mapping, measurable cache speedup, real tool-calling, and clean async architecture | Candidates that skip data fetch or hide mapping failures; unbounded in-memory caches; blocking network I/O |
| Service developer (candidate) | Implementer | Ship a working FastAPI + pydantic-ai solution that survives messy GEO data and defends design trade-offs in discussion | One gene maps to many probes; annotation column names vary; large slow downloads; optional LLM API key |

## Bioinformatics researcher

- **Type:** Primary user
- **Goals:** Ask for 2–5 genes in a chosen GSE and receive usable boxplots plus a concise interpretation; trust that values reflect real GEO data, not model invention; see when probe mapping is partial (how many probes mapped per gene).
- **Pains:** Cannot answer "what is TP53 expression?" directly from a matrix keyed by probes like `1007_s_at`; must find GPL annotation, parse inconsistent files, and decide how to aggregate multiple probes per gene; waiting minutes on every repeat query for the same series/platform; uncertainty when annotations contain multi-gene strings (`TP53 /// WRAP53`) or missing/`---` values.

## Technical assessor / reviewer

- **Type:** Decision-maker (grading / assessment scope)
- **Goals:** Confirm probe→symbol mapping is correct and justified (aggregation, multi-gene cells, missing data); observe a measurable speedup on the second identical request with a bounded eviction policy; see the chatbot invoke a tool and ground its answer in fetched results; review separation of API, service, and external-client layers with specific exception handling.
- **Pains:** Chat replies that look plausible but never called a tool or downloaded GEO data; silent drop of unmapped probes with no surfaced counts; caches that grow without eviction; repeat calls as slow as the first; bare `except` blocks and tangled download/mapping logic in route handlers.

## Service developer (candidate)

- **Type:** Implementer
- **Goals:** Deliver minimum viable endpoints (`POST /chat`, direct expression access e.g. `GET /expression`); implement async I/O for all GEO/network work; document how gene-mapping and caching problems were solved and which trade-offs were chosen; optionally stub the LLM while keeping real tool invocation wiring.
- **Pains:** Real GPL annotation files use unpredictable column names (`Gene Symbol`, `GENE_SYMBOL`, `SYMBOL`, …); engineering two hard problems under time pressure — robust mapping and layered bounded cache (raw file vs parsed map vs per-gene result); choosing cache granularity and eviction without over-engineering; proving cache benefit via timing logs or `cached: true/false` flags.

## Open questions

- Is the primary researcher persona an academic bench scientist, a bioinformatics core-facility analyst, or a mixed audience? (Spec assumes GEO-literate users who know GSE IDs and gene symbols.)
- Will anyone consume the direct REST endpoint only (no chat), e.g. a future frontend or notebook integration?
- Are there compliance constraints (PII, institutional data policies) beyond using public NCBI GEO data?
