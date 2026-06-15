# GEO Expression Service

A small service for exploring gene expression from [NCBI GEO](https://www.ncbi.nlm.nih.gov/geo/): a **FastAPI backend** that downloads expression data for a GEO series, maps platform probes to gene symbols, and builds per-gene boxplots; plus a **pydantic-ai chatbot** that calls that logic via tools (e.g. *"Show me TP53 and BRCA1 expression in GSE2034"*).

The two core engineering problems are **probe → gene mapping** (messy platform annotations, one gene / many probes) and **caching** (GEO downloads are slow; repeat requests must be near-instant with a bounded eviction policy).

## Quick start

From repository root (`ncbi-viewer/`):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e .
cp .env.example .env               # optional — defaults work without .env
python -m uvicorn geo_expression_service.main:app --host 127.0.0.1 --port 8000
```

Or with Make: `make install && make run`.

In another terminal:

```bash
curl -s http://127.0.0.1:8000/health
```

First `/expression` or `/chat` request for a new `(gse, genes)` pair downloads ~60 MB from NCBI — **30–120 seconds** is normal. Repeat requests should show `"cached": true` and lower `duration_ms`.

- **Full install, curl examples, Swagger, troubleshooting:** [docs/run_book.md](docs/run_book.md)
- **OpenAPI (interactive):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) after start
- **Manual acceptance checklist:** [03-Solution/01-solution-draft.md](03-Solution/01-solution-draft.md) · [run book checklist](docs/run_book.md#checklist)

## Design decisions

### Gene mapping

Platform annotations map **probe IDs** (matrix row headers) to **gene symbols** via a GPL SOFT table. The mapper auto-detects a symbol column (`Gene Symbol`, `GENE_SYMBOL`, etc.), splits multi-gene cells on `///` or `//`, and treats empty, `---`, `NA`, and similar tokens as unmapped. When several probes hit the same gene, per-sample values are aggregated with **mean of log2 intensities**; genes with zero mapped probes appear in the response with `probes_mapped: 0` and an explicit `skip_reason` — nothing is silently dropped or fabricated. Tabular parsing uses **stdlib `csv` only** (no pandas): minimal dependencies and fast startup, at the cost of hand-rolled column detection — acceptable because matrices are parsed once per cache miss.

### Cache

A **two-tier cache** (in-memory LRU + disk under `GEO_CACHE_DIR`) sits in front of NCBI downloads at three layers: raw bytes, parsed probe→symbol maps, and final expression results. Keys are bounded by `GEO_CACHE_MAX_ENTRIES` and `GEO_CACHE_MAX_BYTES`; disk entries survive process restart. **Negative caching** avoids re-downloading platforms that fail to parse. Every expression response exposes `cached` and `duration_ms` so repeat calls show measurable speedup. GeoClient adds retries with backoff, HTTP timeouts, and bounded concurrency — see [`.env.example`](.env.example).

Details: [03-Solution/03-architecture.md](03-Solution/03-architecture.md).

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
