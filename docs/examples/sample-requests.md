# Sample Requests

Base URL (dev): `http://127.0.0.1:8000`. Interactive docs: `http://127.0.0.1:8000/docs`.

Deterministic endpoints (overview, anomalies, cross-domain) need **no LLM key**. Agent endpoints (query, investigate, executive-summary) use the configured LLM provider and gracefully return an analytics-backed response if none is configured.

Available months in the shipped dataset: `2026-05`, `2026-06`, `2026-07`.

---

## Deterministic analytics

### Monthly overview
```bash
curl "http://127.0.0.1:8000/api/overview?month=2026-07"
```

### Standard anomalies (existing engine)
```bash
curl "http://127.0.0.1:8000/api/anomalies?month=2026-07&limit=10"
# optional filters:
curl "http://127.0.0.1:8000/api/anomalies?month=2026-07&severity=high&limit=5"
```

### Cross-domain anomalies (new)
```bash
curl "http://127.0.0.1:8000/api/anomalies/cross-domain?month=2026-07&baseline_month=2026-06&limit=20"

# filter by category (billing_integrity | safety_pattern |
#   vendor_operational_divergence | shift_readiness_pattern | data_integrity_anomaly)
curl "http://127.0.0.1:8000/api/anomalies/cross-domain?month=2026-07&category=billing_integrity"

# filter by severity (low | medium | high)
curl "http://127.0.0.1:8000/api/anomalies/cross-domain?month=2026-07&severity=high"
```

### Unified feed (opt-in merge, preserves the Anomaly contract)
```bash
curl "http://127.0.0.1:8000/api/anomalies?month=2026-07&include_cross_domain=true&limit=50"
```

---

## Agentic endpoints (LLM-backed, with deterministic fallback)

### Ask Pulse — free-form question
```bash
curl -X POST "http://127.0.0.1:8000/api/agent/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Why is Aarav Petrov Travel high risk?",
    "month": "2026-07",
    "baseline_month": "2026-06"
  }'
```

Suspicious-pattern phrasing (e.g. *"possible billing irregularity"*, *"suspicious"*, *"reconciliation"*, *"anomalies a normal report would miss"*) is routed to the cross-domain tool automatically.

### Investigate one anomaly
Use an `id` from `/api/anomalies` (`anomaly-…`) or `/api/anomalies/cross-domain` (`cross-…`).
```bash
curl -X POST "http://127.0.0.1:8000/api/agent/investigate" \
  -H "Content-Type: application/json" \
  -d '{
    "anomaly_id": "cross-22a4f39765c4",
    "month": "2026-07"
  }'
```

### Executive summary (leadership brief)
```bash
curl -X POST "http://127.0.0.1:8000/api/reports/executive-summary" \
  -H "Content-Type: application/json" \
  -d '{
    "month": "2026-07",
    "baseline_month": "2026-06"
  }'
```
