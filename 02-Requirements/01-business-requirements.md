# Business requirements

Business outcomes for the **GEO Expression Service**: what value must be delivered and how success is measured. Derived from `01-Context/01-stakeholders.md`, `01-Context/02-scenarios.md`, and `docs/GEO_EXPRESSION_SERVICE_SPEC.md`.

**Upstream gaps:** `01-Context/03-glossary.md` and `01-Context/04-interview-notes.md` are not yet authored. Domain terms below follow stakeholders and scenarios; assumptions and open questions are called out per BR where relevant.

## Contents

- [BR-01 — Per-gene expression boxplots from a chosen GEO series](#br-01-per-gene-expression-boxplots-from-a-chosen-geo-series)
- [BR-02 — Natural-language exploration with data-grounded answers](#br-02-natural-language-exploration-with-data-grounded-answers)
- [BR-03 — Direct programmatic access to the same expression capability](#br-03-direct-programmatic-access-to-the-same-expression-capability)
- [BR-04 — Accurate probe-to-gene mapping on real-world platform annotations](#br-04-accurate-probe-to-gene-mapping-on-real-world-platform-annotations)
- [BR-05 — Mapping coverage transparency](#br-05-mapping-coverage-transparency)
- [BR-06 — Predictable experience on first-time series queries](#br-06-predictable-experience-on-first-time-series-queries)
- [BR-07 — Near-instant repeat queries for the same series and genes](#br-07-near-instant-repeat-queries-for-the-same-series-and-genes)
- [BR-08 — Bounded reuse of expensive GEO fetches](#br-08-bounded-reuse-of-expensive-geo-fetches)
- [BR-09 — Efficient handling of unmappable or low-coverage platforms](#br-09-efficient-handling-of-unmappable-or-low-coverage-platforms)
- [BR-10 — Verifiable assessment deliverable](#br-10-verifiable-assessment-deliverable)
- [BR-11 — Defensible design narrative for mapping and reuse trade-offs](#br-11-defensible-design-narrative-for-mapping-and-reuse-trade-offs)
- [BR-12 — Stable service under concurrent exploratory use](#br-12-stable-service-under-concurrent-exploratory-use)
- [BR-13 — Scoped, validated query contract](#br-13-scoped-validated-query-contract)
- [Coverage summary](#coverage-summary)
- [Revision log](#revision-log)

---

## BR-01 — Per-gene expression boxplots from a chosen GEO series

- **Statement:** A researcher who knows a **GSE** accession and **2–5 gene symbols** can obtain usable **boxplots** of each gene's expression across that study's samples without manually downloading matrices or wrangling probe-level data.
- **Why it matters:**
  - Primary user goal: replace hours of SOFT/Matrix download, GPL lookup, and custom plotting with a single query.
  - Core assessment scope: the service must solve the probe-ID → gene-symbol gap that blocks direct symbol queries against GEO expression matrices.
- **Success criteria:**
  - A valid series + gene list yields a combined visualization covering all requested genes that have mappable data.
  - Output is consumable by a human reviewer or downstream client (renderable image or structured plot data).
  - Expression values reflect the study's published GEO data, not placeholder or invented numbers.
- **Constraints:** Public NCBI GEO data only; researcher supplies a known GSE and gene symbols (no series discovery by keyword in v1).
- **Notes / open questions:** Is one combined plot per request sufficient, or must each gene appear in a separate chart?

---

## BR-02 — Natural-language exploration with data-grounded answers

- **Statement:** A researcher can ask for expression in **plain language** (e.g. naming a series and genes) and receive a **plot plus a short interpretation** that is grounded in fetched GEO results—not a plausible answer the model could invent without data.
- **Why it matters:**
  - Matches scenario **S-01** and the primary exploratory workflow for bench and bioinformatics users.
  - Assessors grade zero when chat replies look correct but no expression data was retrieved.
- **Success criteria:**
  - A typical natural-language prompt naming a GSE and 2–5 genes produces both a plot artifact and narrative text consistent with the retrieved expression outcome.
  - Reviewer can confirm the answer depended on a real expression lookup, not model recall alone.
  - When the prompt lacks a recognizable series or gene list, the user receives a clear clarification request rather than a fabricated plot.
- **Constraints:** No clinical decision support; exploratory use on public data only.
- **Notes / open questions:** Is streaming delivery required for pass, or is a single complete response acceptable?

---

## BR-03 — Direct programmatic access to the same expression capability

- **Statement:** Users who prefer **scripts, notebooks, or integrations** can request expression boxplots **without** the conversational layer and receive the same underlying data quality and mapping behavior as the chat path.
- **Why it matters:**
  - Scenario **S-02**: automation, smoke tests, and future frontends must not depend on an LLM.
  - Prevents divergent logic that would erode trust in either channel.
- **Success criteria:**
  - A programmatic call with the same GSE and genes returns equivalent plots and mapping metadata as the chat-driven path.
  - Reviewers can validate core expression behavior without an LLM API key.
- **Constraints:** Input contract matches BR-01 (GSE + 2–5 genes).
- **Notes / open questions:** Will a first-party UI consume this path, or is API-only access sufficient for v1?

---

## BR-04 — Accurate probe-to-gene mapping on real-world platform annotations

- **Statement:** Expression results correctly translate **probe-level matrices** into **per-gene values** despite messy GPL annotations—multiple probes per gene, multi-gene cells, varying column names, and missing or sentinel values.
- **Why it matters:**
  - Central evaluation criterion in the task spec; primary user pain when working with GEO manually.
  - Wrong or arbitrary mapping undermines every downstream plot and interpretation.
- **Success criteria:**
  - A documented, defensible rule aggregates multiple probes per gene (e.g. central tendency of log-transformed values).
  - Multi-gene annotation cells (e.g. `TP53 /// WRAP53`) resolve sensibly when the requested symbol is present.
  - Common column-name variants and null/`---`/empty values are handled without crashing or discarding the entire matrix.
  - Mapping choices and trade-offs are explainable to a reviewer in design discussion.
- **Constraints:** Decisions must be justified for assessment, not hidden implementation detail.
- **Notes / open questions:** None beyond aggregation policy documentation (see BR-11).

---

## BR-05 — Mapping coverage transparency

- **Statement:** Every expression outcome **surfaces how well probes mapped** to requested genes—per-gene counts and overall unmapped probe visibility—so users never face a silent total loss of data without explanation.
- **Why it matters:**
  - Stakeholder pain: silent drops when annotations are messy destroy trust.
  - Scenario **S-03** and **S-05** require users to distinguish "slow network" from "nothing mapped."
- **Success criteria:**
  - Response includes per-gene mapping statistics (e.g. probes used, zero-map reason when applicable).
  - Unmapped or skipped probes are reported in aggregate, not omitted from the outcome.
  - When zero probes map for a requested gene, that gene appears explicitly with a stated reason—not omitted as if it were never asked for.
- **Constraints:** Transparency is a non-negotiable trust requirement for assessment.
- **Notes / open questions:** Should partial mapping (some genes mapped, others not) still deliver a plot for mapped genes, or fail the whole request?

---

## BR-06 — Predictable experience on first-time series queries

- **Statement:** The **first request** for a new GSE or platform may take substantial time because GEO downloads are inherently slow, but the user can **distinguish normal cold-path latency** from failure and receives a complete outcome when data is available.
- **Why it matters:**
  - Scenario **S-03**: cold path is expected; frustration comes from opaque hangs or unexplained errors.
  - Sets realistic expectations so researchers accept minutes on first load but not on repeats (BR-07).
- **Success criteria:**
  - First-time queries for a valid public series complete with plots and mapping stats within a bounded wait (timeouts prevent indefinite hangs).
  - Failures (network, missing series, parse errors) return understandable outcomes rather than generic crashes.
  - Duration or cache-miss indication is observable so users and assessors can see cold vs warm behavior.
- **Constraints:** Sub-second first request is not a business goal; GEO file size drives baseline latency.
- **Notes / open questions:** None.

---

## BR-07 — Near-instant repeat queries for the same series and genes

- **Statement:** An **identical repeat request** (same GSE, same genes, same platform context) completes **measurably faster** than the first call—fast enough that researchers do not wait through full GEO download again.
- **Why it matters:**
  - Second core evaluation problem in the task spec; scenario **S-04**.
  - Primary user pain: repeat visits and iterative exploration should not re-pay full download cost every time.
- **Success criteria:**
  - Second identical request shows order-of-magnitude latency reduction vs the cold path (verifiable via timing or an explicit cache-hit indicator).
  - Plot and mapping outcomes match the first call for the same inputs.
  - Speedup is demonstrable to an assessor without specialized tooling (logs or response metadata suffice).
- **Constraints:** Speedup must be real and observable, not anecdotal.
- **Notes / open questions:** Must warm results survive a service restart for full credit, or is within-session reuse alone acceptable if eviction and speedup are demonstrated?

---

## BR-08 — Bounded reuse of expensive GEO fetches

- **Statement:** Reuse of downloaded GEO and annotation data is **bounded** with a clear **eviction policy**, so the service remains stable under repeated distinct queries without unbounded memory or disk growth.
- **Why it matters:**
  - Assessor pain: an unbounded in-memory dict is not a cache and fails the assessment criterion.
  - Scenario **S-04** and **S-07**: shared reuse must not trade away operational safety.
- **Success criteria:**
  - Cache capacity is limited by configurable entry count, size, or equivalent business rule.
  - When limits are exceeded, older entries are evicted predictably (e.g. least-recently-used semantics).
  - Service continues to respond correctly after sustained load with many distinct series/gene combinations.
- **Constraints:** Unbounded growth is unacceptable for assessment pass.
- **Notes / open questions:** Any institutional policy on how long third-party GEO files may be retained locally?

---

## BR-09 — Efficient handling of unmappable or low-coverage platforms

- **Statement:** When a platform or gene set **cannot be mapped** (or maps only partially), the user receives a **clear, structured outcome** and **repeat requests do not re-incur** the full cost of discovering that dead end.
- **Why it matters:**
  - Scenario **S-05**: wrong platform, retired arrays, or empty symbol columns are real GEO outcomes.
  - Without negative reuse, every repeat wastes download time on a known-bad platform.
- **Success criteria:**
  - Unmappable or zero-hit outcomes include mapping stats and per-gene failure reasons.
  - A second identical request for a known-unmappable case completes quickly from stored negative outcome.
  - User understands why a plot is empty or partial without a generic error page.
- **Constraints:** Must not fabricate expression values to fill gaps.
- **Notes / open questions:** Aligns with BR-05 open question on partial vs whole-request failure.

---

## BR-10 — Verifiable assessment deliverable

- **Statement:** The implementer delivers a **runnable, shareable repository** before assessment day so reviewers can independently verify mapping, caching, grounded chat behavior, and operational instructions.
- **Why it matters:**
  - Task spec requires repo link at least one day in advance.
  - Technical assessor stakeholder needs reproducible evidence, not slide-deck claims.
- **Success criteria:**
  - Repository link shared ≥1 day before assessment.
  - A reviewer following documented run instructions can start the service and exercise both conversational and direct expression paths.
  - Evidence exists for tool-grounded chat (trace, logs, or equivalent observable proof).
- **Constraints:** Assessment timeline is non-negotiable.
- **Notes / open questions:** None.

---

## BR-11 — Defensible design narrative for mapping and reuse trade-offs

- **Statement:** Stakeholders can read **why** probe aggregation, multi-gene handling, cache layering, and eviction were chosen—not only **how** to start the service.
- **Why it matters:**
  - Grading explicitly includes README quality and design-discussion defensibility (scenario **S-06**).
  - Separates candidates who understand trade-offs from those who only pass smoke tests.
- **Success criteria:**
  - Documentation includes distinct explanations of the gene-mapping problem and the reuse/caching problem, each with stated trade-offs.
  - A reviewer can challenge aggregation or cache-layer choices and receive coherent rationale aligned with implemented behavior.
- **Constraints:** Narrative must match actual behavior (no documentation drift).
- **Notes / open questions:** None.

---

## BR-12 — Stable service under concurrent exploratory use

- **Statement:** Multiple researchers or automated clients can issue **overlapping expression queries** without the service failing catastrophically or corrupting shared reuse state.
- **Why it matters:**
  - Scenario **S-07**: demos, parallel fetches, and NCBI rate limits make uncontrolled fan-out a business risk.
  - Cold-path slowness must not block all users when one large download is in flight.
- **Success criteria:**
  - Concurrent requests for different series complete with isolated failure domains (one bad download does not take down unrelated queries).
  - Parallel external fetches are limited to a bounded concurrency level appropriate for shared NCBI access.
  - Recoverable download failures retry within a reasonable budget before surfacing error to the user.
- **Constraints:** Throughput improvement must not come at the cost of overwhelming external GEO infrastructure or local resource exhaustion.
- **Notes / open questions:** Expected concurrency for assessment—single reviewer vs small team demo?

---

## BR-13 — Scoped, validated query contract

- **Statement:** Each expression request is limited to a **valid GSE identifier** and **2–5 unique gene symbols**, with clear rejection when inputs fall outside that contract.
- **Why it matters:**
  - Task spec and stakeholder table define explicit input bounds; prevents open-ended scope creep.
  - Early validation protects users from long GEO fetches that cannot succeed.
- **Success criteria:**
  - Requests outside the gene-count range are rejected before expensive GEO work begins, with an understandable message.
  - Malformed or invalid series identifiers are rejected or failed with specific feedback—not a silent empty plot.
  - Gene symbols are normalized consistently (e.g. case) so repeat queries match for reuse (BR-07).
- **Constraints:** Gene discovery, arbitrary GEO browsing, and lists larger than five genes are out of scope for v1.
- **Notes / open questions:** None.

---

## Coverage summary

| Scenario | Primary BR themes |
| --- | --- |
| S-01 Natural-language chat | BR-01, BR-02, BR-04, BR-05 |
| S-02 Direct programmatic access | BR-01, BR-03, BR-04, BR-05 |
| S-03 Cold path / first request | BR-04, BR-05, BR-06, BR-13 |
| S-04 Warm cache / repeat request | BR-07, BR-08 |
| S-05 Negative / unmappable platform | BR-05, BR-09 |
| S-06 Assessor validation | BR-02, BR-10, BR-11 |
| S-07 Concurrent load | BR-08, BR-12 |

## Revision log

- 2026-06-15 — Initial business requirements from stakeholders, scenarios, and GEO expression service task spec (glossary and interview notes pending).
