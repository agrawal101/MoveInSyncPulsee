# Scalability

## Current (hackathon) implementation

```
CSV → preprocessing → Parquet → DuckDB → aggregated analytical queries
                                              ↓
                              cross-domain anomaly engine
                                              ↓
                                  LangGraph agent service
                                              ↓
                                      FastAPI → React UI
```

- Single-file embedded warehouse (DuckDB), read-only at serve time.
- Aggregate tables precomputed once by `scripts/build_analytics.py`.
- Detection runs on demand per request; sub-second aggregate scans.
- Single tenant; LLM provider pluggable (Sarvam / OpenAI / Anthropic) and optional.

This is deliberately simple: it makes the system **reproducible and auditable**, which is the point of a deterministic-analytics product.

## Production evolution (NOT implemented)

```
Data ingestion → S3 data lake → processing / streaming →
warehouse / operational store → feature & aggregate layer →
anomaly engine → agent service → APIs
```

### Ingestion & storage
- **S3 data lake** for raw feeds; **Aurora/PostgreSQL** or a columnar warehouse for served aggregates.
- **Incremental processing** — only new partitions are reprocessed, not the whole history.
- **Precomputed aggregates** refreshed on a schedule so queries stay O(months), not O(rows).

### Detection cadence
- **Scheduled detection** (e.g. nightly) writing an anomaly feed.
- **Event-driven detection** on new billing/safety batches for near-real-time flags.

### Multi-tenancy
- Tenant isolation at storage and query layers; per-tenant thresholds; RBAC on APIs and actions.

### Latency & cost
- **Caching** of aggregate and anomaly results; precomputed feeds so the request path is a read.
- **LLM token minimization** — see below.

### Observability & governance
- Metrics/traces for detection latency, anomaly volume, token spend; audit logging of every recommended action; a model gateway for provider routing and rate limits.

## Why the LLM cost/latency/privacy story scales

The model receives **compact, structured, ID-tagged evidence — not millions of raw records.** `compact_evidence()` caps what crosses to the model to top-N aggregate rows per tool.

This directly improves:

- **Cost** — token count is bounded by the number of aggregates, not dataset size.
- **Latency** — small prompts synthesize fast; bounded repair prevents runaway loops.
- **Privacy** — raw trip/employee rows never leave the deterministic layer.
- **Grounding** — a small, exact evidence set is far easier to validate than free-form context, which is why numeric validation is tractable.

## Data-volume posture

Because analytics operate on **aggregate tables**, scaling raw volume mostly affects preprocessing/aggregation (batch, parallelizable), not the serve path. The anomaly engine and agent already work over per-entity aggregates, so their cost grows with the number of vendors/shifts, not the number of trips.
