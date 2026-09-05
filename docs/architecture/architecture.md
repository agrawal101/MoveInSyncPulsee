# Architecture

MoveInSync Pulse is a **deterministic-analytics-first** mobility intelligence system with a **grounded LLM narration layer**. The design principle running through every layer:

> **The LLM never calculates operational metrics.** Deterministic SQL/Python computes every number; the anomaly engine detects every pattern; the agent decides what evidence to gather; the LLM only explains that evidence and recommends qualitative next actions.

See [architecture.svg](architecture.svg) (rendered) and [architecture.mmd](architecture.mmd) (Mermaid source).

---

## 1. Layered data flow

```
CSV sources → data quality & normalization → DuckDB/Parquet →
deterministic analytics → cross-domain anomaly engine →
LangGraph orchestrator → grounded LLM synthesis →
numeric validation/fallback → FastAPI → React UI → human review
```

### Data sources
Five domains: trips (`rides`), employee/boarding (`employees`), safety (`alerts`), billing (`bills`), feedback (`feedback`).

### Data quality & normalization
`app/data/preprocessing.py` reconciles heterogeneous schemas, normalizes trip IDs and timestamps, and stamps per-row quality flags (`q_zero_distance`, `q_negative_distance`, `q_invalid_timestamp`, missing-join detection, invalid severity). Quality is a **first-class output**, not a silent filter.

### DuckDB + Parquet
Normalized rows are written to Parquet and loaded into a single DuckDB file (`data/processed/mobility.duckdb`). `app/analytics/aggregates.py` precomputes aggregate tables (`monthly_metrics`, `vendor_monthly_metrics`, `shift_monthly_metrics`, `cost_monthly_metrics`, `vendor_safety_metrics`, …).

---

## 2. Why DuckDB + Parquet

- **Zero-ops embedded OLAP.** No server to run for a hackathon; the whole warehouse is one file. Columnar execution gives sub-second aggregate scans over the full dataset.
- **Parquet as the interchange format.** Compressed, columnar, portable; the same files feed both preprocessing validation and DuckDB.
- **SQL is the right tool for the job.** The core problem is structured analytical reasoning (group-bys, window ranks, joins across domains) — DuckDB expresses that directly and reproducibly, which matters because reproducibility is the trust anchor of the whole system.
- **Read-only at serve time.** The API opens DuckDB read-only, so analytics can never mutate state during a request.

---

## 3. Deterministic analytics vs generative AI (the separation)

| Concern | Owner | Guarantee |
|---|---|---|
| Metric values (rates, costs, counts, changes) | SQL/Python in `AnalyticsService` | Exact, reproducible, testable |
| Pattern detection | `anomaly_detection.py` + `cross_domain_anomalies.py` | Threshold-based, deterministic, sample-protected |
| Which evidence to gather | LangGraph plan | Rule-based tool routing |
| Explanation, interpretation, recommendation | LLM | Bound to supplied evidence only |

The LLM receives **compact structured evidence with IDs**, never raw records, and every numeric claim it emits is validated back against that evidence (§7). If validation fails or the provider is down, the system returns a deterministic analytics-backed answer instead.

---

## 4. Cross-domain anomaly engine

`app/analytics/cross_domain_anomalies.py`. This is the core product innovation: anomalies that are invisible in any single dashboard and only emerge when domains are correlated.

- Builds a **per-entity signal model** (vendor, shift) from existing aggregates + bill-quality flags + rides-derived utilization/distance.
- Five detectors: `billing_integrity`, `safety_pattern`, `vendor_operational_divergence`, `shift_readiness_pattern`, `data_integrity_anomaly`.
- **Historical** (vs baseline month) and **peer** (vs eligible-vendor median) benchmarking.
- **Sample-size protection** (`MIN_VENDOR_TRIPS`, `MIN_SHIFT_SAMPLE`, `MIN_BILL_ROWS` = 500).
- **Explainable `cross_signal_risk_score`** (0–100) = `historical_deviation + correlated_signals + peer_deviation + data_confidence`; every component is returned.

Full method detail: [../product/anomaly-methodology.md](../product/anomaly-methodology.md).

---

## 5. Why LangGraph — and why ONE orchestrating agent

LangGraph models the investigation as an explicit state graph: `plan → collect_evidence → check_quality → synthesize`. This gives **deterministic control flow** (which tools run, in what order) while keeping the LLM confined to the final synthesis node.

We deliberately use **one orchestrating agent**, not a multi-agent swarm, because:

- The task is bounded — a fixed catalogue of deterministic tools over one warehouse. Multiple autonomous agents would add coordination overhead, non-determinism, and token cost with no analytical gain.
- Determinism is a feature. A single planned graph is auditable and reproducible; the tools called for a given anomaly are predictable and testable.
- The intelligence lives in the **deterministic engine**, not in agent negotiation. The agent's job is evidence selection, not reasoning about numbers.

---

## 6. Evidence grounding & evidence IDs

`app/agents/evidence.py`:

- `compact_evidence()` bounds what the model sees to aggregate, decision-grade rows (e.g. top anomalies by severity, top vendors, eligible shifts) — never trip-level rows.
- `attach_evidence_ids()` stamps a stable `evidence_id` next to every aggregate value (e.g. `ev_vendor_aarav_petrov_travel_alerts_per_1000_trips_2026_07`). The model must copy an `evidence_id` for any number it cites.

This is what makes numeric claims traceable end-to-end from the UI back to a deterministic aggregate.

---

## 7. Numeric validation, repair, and fallback

`app/agents/validation.py` + `app/agents/graph.py`:

1. **Schema** — the provider must return a strict Pydantic schema (`AgentSynthesis`); each finding requires `evidence_id`, `metric`, `current_value`.
2. **Value validation** — every populated numeric role (current/baseline/change/relative/sample) must match the referenced `evidence_id` within tolerance, or the response is rejected.
3. **Prose sanitation** — operational numbers are stripped from narrative text; they may only live in structured fields.
4. **Bounded repair** — on rejection the agent gets exactly one conservative repair attempt.
5. **Deterministic fallback** — if the provider errors or repair still fails, `app/agents/fallback.py` builds an analytics-backed response from the same evidence. **The dashboard and investigations therefore work with no LLM key at all.**

---

## 8. Data-quality propagation

Warnings flow from preprocessing → analytics (`data_quality_warnings` on every model) → `check_quality` graph node → agent response. The UI surfaces them as caveats. Nothing is silently dropped: e.g. zero-distance bill rows are excluded from cost/km **and** the exclusion is disclosed.

---

## 9. API / UI separation

- **Backend** (`app/`) — FastAPI, stateless, read-only DuckDB, CORS locked to the dev frontend origin.
- **Frontend** (`frontend/`) — React + TypeScript + Vite + Tailwind; talks only to the REST API via a typed client. No business logic in the UI.

---

## 10. Hackathon architecture vs production evolution

**Implemented today (hackathon):** CSV → preprocessing → Parquet → DuckDB → aggregate tables → deterministic analytics → cross-domain engine → LangGraph → grounded LLM → FastAPI → React. Single-file warehouse, single tenant, on-demand detection, pluggable LLM provider (Sarvam / OpenAI / Anthropic).

**Future (NOT implemented — production roadmap):**

- **Ingestion:** AWS S3 data lake; scheduled + event-driven streams instead of manual CSV runs.
- **Storage:** Aurora/PostgreSQL operational store or a warehouse; incremental/precomputed aggregates.
- **Workflow:** durable workflows (e.g. Temporal) for approval and corrective-action follow-through.
- **Multi-tenancy:** tenant isolation, RBAC, per-tenant thresholds.
- **Governance:** audit logging, a model gateway for provider routing/rate-limiting, PII controls.
- **Observability:** metrics/traces on detection latency and token spend.

These are explicitly **future architecture**, not current capabilities.
