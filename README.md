# GEO Expression Service

A small service for exploring gene expression from [NCBI GEO](https://www.ncbi.nlm.nih.gov/geo/): a **FastAPI backend** that downloads expression data for a GEO series, maps platform probes to gene symbols, and builds per-gene boxplots; plus a **pydantic-ai chatbot** that calls that logic via tools (e.g. *"Show me TP53 and BRCA1 expression in GSE2034"*).

The two core engineering problems are **probe → gene mapping** (messy platform annotations, one gene / many probes) and **caching** (GEO downloads are slow; repeat requests must be near-instant with a bounded eviction policy).

## Start here

Read the numbered folders in order — each layer builds on the previous one:

1. **[01-Context/](01-Context/)** — domain background: GSE (series), GSM (sample), GPL (platform), expression matrices, and why probe IDs must be mapped to gene symbols.
2. **[02-Requirements/](02-Requirements/)** — what the service must do: API endpoints, chatbot tool-calling, mapping robustness, cache behavior, and grading criteria.
3. **[03-Solution/](03-Solution/)** — architecture, vertical slices, and implementation decisions (aggregation, cache layers, async I/O).
4. **[04-UI/](04-UI/)** — UI vision, design system, and mockups for the chatbot experience.

## Documentation

| Folder | Purpose |
|--------|---------|
| [01-Context/](01-Context/) | Domain glossary, stakeholders, scenarios |
| [02-Requirements/](02-Requirements/) | Business and system requirements |
| [03-Solution/](03-Solution/) | Solution draft, architecture, backlog |
| [04-UI/](04-UI/) | Design system, mockups ([mockups/](04-UI/mockups/)) |
| [docs/run_book.md](docs/run_book.md) | Install, run, and verify the API locally |

## Implementation

Python package: [geo_expression_service/](geo_expression_service/) (`GET /health`, `GET /expression`).

Quick start (from repository root):

```bash
make install    # create .venv + pip install -e .
make run        # start API on http://127.0.0.1:8000
make health     # verify GET /health (in another terminal)
```

Manual setup (without Make):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -e .
python -m uvicorn geo_expression_service.main:app --host 127.0.0.1 --port 8000
```

| Make target | Description |
|-------------|-------------|
| `make help` | List all commands |
| `make install` | Create `.venv` and install dependencies |
| `make install-dev` | Install with pytest and ruff |
| `make lint` | Run ruff linter |
| `make format` | Auto-format with ruff |
| `make fix` | Auto-fix lint issues + format |
| `make check` | Lint + pytest |
| `make run` | Start uvicorn |
| `make run-dev` | Start uvicorn with `--reload` |
| `make test` | Run `pytest -v` |
| `make health` | Curl `/health` |
| `make plot` | Save expression PNG (`GSE`, `GENES` env vars) |

See [docs/run_book.md](docs/run_book.md) for full instructions.
