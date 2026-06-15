# GEO Expression Service

A small service for exploring gene expression from [NCBI GEO](https://www.ncbi.nlm.nih.gov/geo/): a **FastAPI backend** that downloads expression data for a GEO series, maps platform probes to gene symbols, and builds per-gene boxplots; plus a **pydantic-ai chatbot** that calls that logic via tools (e.g. *"Show me TP53 and BRCA1 expression in GSE2034"*).

The two core engineering problems are **probe → gene mapping** (messy platform annotations, one gene / many probes) and **caching** (GEO downloads are slow; repeat requests must be near-instant with a bounded eviction policy).

## Quick start (clean environment)

From repository root (`ncbi-viewer/`):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e .
cp .env.example .env               # optional — defaults work without .env
python -m uvicorn geo_expression_service.main:app --host 127.0.0.1 --port 8000
```

Or with Make: `make install && make run`.

Verify all three endpoints (server must be running in another terminal):

```bash
curl -s http://127.0.0.1:8000/health

curl -s --max-time 300 \
  "http://127.0.0.1:8000/expression?gse=GSE2034&genes=TP53,BRCA1"

curl -s --max-time 300 -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me TP53 and BRCA1 expression in GSE2034"}'
```

First `/expression` or `/chat` request for a new `(gse, genes)` pair downloads ~60 MB from NCBI — **30–120 seconds** is normal. Repeat requests should show `"cached": true` and lower `duration_ms`.

Full install, troubleshooting, Swagger, and PowerShell examples: **[docs/run_book.md](docs/run_book.md)**.

OpenAPI (interactive): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) after start.

## Design: gene mapping

Platform annotations map **probe IDs** (matrix row headers) to **gene symbols** via a GPL SOFT table. The mapper (`domain/annotation_mapper.py`) auto-detects a symbol column (`Gene Symbol`, `GENE_SYMBOL`, etc.), splits multi-gene cells on `///` or `//` (e.g. `TP53 /// TP53-AS1`), and treats empty, `---`, `NA`, and similar tokens as unmapped. When several probes hit the same gene, per-sample values are aggregated with **mean of log2 intensities** (`mean_log2`); genes with zero mapped probes appear in the response with `probes_mapped: 0` and an explicit `skip_reason` — nothing is silently dropped or fabricated.

Tabular parsing uses **stdlib `csv` only** (no pandas). That keeps the dependency surface minimal and startup fast for an API service, at the cost of hand-rolled column detection and no vectorized math — acceptable here because matrices are parsed once per cache miss and aggregation runs over small probe sets per gene.

## Design: cache

A **two-tier CacheStore** (`adapters/cache_store.py`) sits in front of GeoClient:

1. **In-memory LRU** — hot keys promoted on disk hit; evicted by `GEO_CACHE_MAX_ENTRIES` and `GEO_CACHE_MAX_BYTES`.
2. **Disk tier** under `GEO_CACHE_DIR` — survives process restart; entries carry `schema_version: 1` (mismatch → delete-on-read).

Keys: `raw:{url_hash}` (downloaded bytes), `map:{gpl_id}` (parsed probe→symbol table), `result:{gse_id}:{genes_hash}` (full `ExpressionResult`; gene list sorted + uppercased for the hash). **Negative caching** stores a sentinel when GPL parse/fetch fails so repeated bad requests fail fast without a download storm. The API exposes `cached: true/false` and `duration_ms` on every expression response (including chat tool results).

GeoClient adds **retries with backoff**, **HTTP timeout** (`GEO_HTTP_TIMEOUT_S`), and a **bounded semaphore** (`GEO_CONCURRENCY_LIMIT`) for parallel matrix + annotation fetches — see `.env.example`.

## Validation and chat behavior

| Rule | Behavior |
|------|----------|
| GSE format | Uppercase `GSE` + digits; malformed → HTTP **422** (`invalid_gse_format`) |
| Gene count | **2–5** unique symbols (case-insensitive); otherwise HTTP **422** (`invalid_gene_count`) |
| Stub LLM | Default when `OPENAI_API_KEY` is absent or `GEO_STUB_LLM=true`; **ExpressionTool still runs** with real GEO data |
| Chat clarification | Message without recognizable GSE + 2–5 genes → HTTP **200**, `tool_invoked: false`, `expression: null`, helpful text (not an error) |
| Chat tool validation failure | e.g. LLM passes 1 gene → HTTP **422** (same as `/expression`) |

## Configuration

Copy [`.env.example`](.env.example) to `.env` in repository root. All `GEO_*` keys are documented there and match `geo_expression_service/config.py`.

## Acceptance checklist (manual verification)

Cross-reference with [03-Solution/01-solution-draft.md](03-Solution/01-solution-draft.md) — Part A acceptance themes:

| Theme | How to verify (README / OpenAPI / run book) |
|-------|---------------------------------------------|
| **Happy path expression** | `GET /expression?gse=GSE2034&genes=TP53,BRCA1` → HTTP 200, PNG base64 plot ([run book §6](docs/run_book.md#step-07-expression)) |
| **Gene count bounds** | 1 or 6 genes → HTTP 422 before GEO I/O ([run book §9](docs/run_book.md#step-08-errors)) |
| **Mapping transparency** | Response `mapping.per_gene` + `unmapped_probe_count`; zero probes → `skip_reason` |
| **Multi-gene cells** | Covered by `tests/test_annotation_mapper.py`; mapper splits `///` |
| **Cache cold/warm** | First request `cached: false`; identical second → `cached: true`, lower `duration_ms` ([run book §7](docs/run_book.md#step-08-chat)) |
| **Cache survives restart** | Stop uvicorn, restart, repeat request — disk tier avoids full re-download |
| **Bounded cache** | `GEO_CACHE_MAX_ENTRIES` / `GEO_CACHE_MAX_BYTES`; see `tests/test_cache_store.py` |
| **Chat happy path + tool** | `POST /chat` → `tool_invoked: true`, plot in `expression`; logs show `ExpressionTool invoked` |
| **Stub LLM** | No API key → templated `message`, real plot |
| **Parse failure / clarification** | Vague message → HTTP 200, `tool_invoked: false` ([run book §7](docs/run_book.md#chat-clarification)) |
| **Resilience** | Timeout/retry/concurrency via `GEO_HTTP_*` and `GEO_CONCURRENCY_LIMIT`; `502`/`504` on upstream failure |
| **README run** | This section + [run book checklist §14](docs/run_book.md#step-13-checklist) |

Recommended tests (non-blocking): `make test` or `pytest -v` — mapping unit tests, cache LRU/disk/negative cache, chat stub path (`tests/`).

## Project documentation

| Folder | Purpose |
|--------|---------|
| [01-Context/](01-Context/) | Domain glossary, stakeholders, scenarios |
| [02-Requirements/](02-Requirements/) | Business and system requirements |
| [03-Solution/](03-Solution/) | Solution draft, architecture, backlog |
| [04-UI/](04-UI/) | Design system, mockups |
| [docs/run_book.md](docs/run_book.md) | Install, run, curl/Swagger, troubleshooting |

## Implementation

Python package: [geo_expression_service/](geo_expression_service/) — `GET /health`, `GET /expression`, `POST /chat`.

| Make target | Description |
|-------------|-------------|
| `make help` | List all commands |
| `make install` | Create `.venv` and install dependencies |
| `make install-dev` | Install with pytest and ruff |
| `make run` | Start uvicorn on :8000 |
| `make test` | Run `pytest -v` |
| `make health` | Curl `/health` (server must be running) |
| `make check` | Lint + pytest |

See [docs/run_book.md](docs/run_book.md) for full instructions.
