# Sample Responses

All payloads below are **real output from the shipped dataset (July 2026)**, captured via the API / deterministic engine. Numbers are not invented. Long arrays are trimmed for readability where noted.

---

## `GET /api/overview?month=2026-07` (trimmed)

```jsonc
{
  "month": "2026-07",
  "previous_month": "2026-06",
  "baseline_month": "2026-05",
  "metrics": {
    "total_trips":         { "current_value": 215885, "previous_value": 210669, "unit": "count" },
    "delay_rate":          { "current_value": 0.0904,  "previous_value": 0.1195, "unit": "rate" },
    "no_show_rate":        { "current_value": 0.0542,  "previous_value": 0.0756, "unit": "rate" },
    "alerts_per_1000_trips": { "current_value": 73.3446, "previous_value": 71.9565, "unit": "per_1000_trips" },
    "total_billing_amount": { "current_value": 294558341.70, "previous_value": 284809881.83, "unit": "currency_units" }
    // …additional metrics omitted
  },
  "data_quality_warnings": [
    { "code": "rating_zero_semantics",
      "message": "Zero ratings excluded from non-zero rating metric; may mean not-rated/not-applicable." }
  ]
}
```

---

## `GET /api/anomalies?month=2026-07&limit=1` (existing engine — contract unchanged)

```json
{
  "id": "anomaly-9cf031d55ec4",
  "category": "vendor_performance",
  "entity_type": "vendor",
  "entity_name": "Aarav Petrov Travel",
  "metric": "alerts_per_1000_trips",
  "current_value": 139.1802,
  "baseline_value": 89.8831,
  "absolute_change": 49.2971,
  "relative_change_pct": 54.85,
  "severity": "high",
  "confidence": "high",
  "sample_size": 5245,
  "reason": "alerts_per_1000_trips deteriorated versus 2026-06 under deterministic threshold.",
  "supporting_dimensions": { "month": "2026-07", "baseline_month": "2026-06", "peer_rank": 15 },
  "data_quality_warnings": []
}
```

---

## `GET /api/anomalies/cross-domain?month=2026-07&baseline_month=2026-06&limit=1` (new)

The strongest real July anomaly — a **safety divergence**: alerts up sharply while service metrics improved.

```json
{
  "id": "cross-22a4f39765c4",
  "category": "safety_pattern",
  "entity_type": "vendor",
  "entity_name": "Aarav Petrov Travel",
  "title": "Safety divergence",
  "severity": "high",
  "confidence": "high",
  "cross_signal_risk_score": 91.0,
  "signals": [
    { "metric": "safety_alert_rate_change", "current_value": 49.2971, "baseline_value": 0.0,
      "peer_median": null, "relative_change_pct": 54.85, "direction": "worse", "weight": 25.0,
      "note": "Safety alert frequency rose materially." },
    { "metric": "no_show_change", "current_value": -0.0488, "direction": "better", "weight": 6.0,
      "note": "No-show performance improved." },
    { "metric": "delay_rate_change", "current_value": -0.0043, "direction": "better", "weight": 6.0,
      "note": "Delay performance improved." },
    { "metric": "safety_alerts_per_1000_trips", "current_value": 139.18, "peer_median": 68.62,
      "direction": "worse", "weight": 10.0, "note": "Alert rate exceeds peer median." }
  ],
  "why_flagged": "Safety alert frequency increased materially despite steady or improving delay and no-show performance, indicating a safety-specific deterioration rather than broad service decline.",
  "recommended_investigation": [
    "Break the alert increase down by alert type, office, and repeated vehicle.",
    "Confirm acknowledgement times and whether alerts cluster in specific windows.",
    "Keep improving delay/no-show trends separate from the safety concern."
  ],
  "risk_components": [
    { "name": "historical_deviation", "value": 45.0, "detail": "Weighted magnitude of signals moving versus baseline." },
    { "name": "correlated_signals",   "value": 20.0, "detail": "4 signals moved together across domains." },
    { "name": "peer_deviation",       "value": 18.0, "detail": "Alert rate vs peer median." },
    { "name": "data_confidence",      "value": 8.0,  "detail": "Vendor trip sample supports the safety comparison." }
  ],
  "sample_size": 5245,
  "month": "2026-07",
  "baseline_month": "2026-06",
  "data_quality_warnings": []
}
```

A real **billing_integrity** example (from `?category=billing_integrity`): *Aarav Petrov Travel — "Potential billing irregularity"*, flagged because billing rose materially **while valid travelled-distance coverage (≈5%) was too low to reconcile cost.** `why_flagged` ends: *"…requires billing reconciliation review; it is a potential irregularity to investigate, not a confirmed finding."*

---

## `POST /api/agent/investigate` — `{"anomaly_id":"cross-22a4f39765c4","month":"2026-07"}`

> **Labeled example — deterministic analytics-backed synthesis** (captured with no LLM provider configured, i.e. the guaranteed fallback path; §17 forbids live LLM calls during packaging). With a provider configured, the same evidence is narrated by the LLM and `synthesis_mode` becomes `"llm"`. Numbers are identical either way — they come from the engine, not the model.

```jsonc
{
  "summary": "Aarav Petrov Travel: Safety divergence requires investigation.",
  "answer": "Multiple deterministic signals moved together across domains. This is a potential pattern that warrants investigation; it is not a confirmed conclusion. Review the correlated evidence before acting.",
  "severity": "high",
  "confidence": "high",
  "synthesis_mode": "deterministic_fallback",
  "findings": [
    { "title": "Safety divergence", "metric": "cross_signal_risk_score", "current_value": 91.0, "sample_size": 5245 },
    { "title": "Correlated signal: safety alert rate change", "metric": "safety_alert_rate_change", "current_value": 49.2971 },
    { "title": "Correlated signal: no show change", "metric": "no_show_change", "current_value": -0.0488 },
    { "title": "Correlated signal: delay rate change", "metric": "delay_rate_change", "current_value": -0.0043 }
  ],
  "recommended_actions": [ /* the anomaly's recommended_investigation steps, approval-gated */ ],
  "data_quality_warnings": [
    "Zero-distance bill rows are excluded from normalized cost metrics.",
    "Severity includes invalid or missing values."
  ],
  "execution": {
    "tools_called": [
      "detect_cross_domain_anomalies_tool",
      "analyze_vendor_tool",
      "analyze_safety_alerts_tool",
      "analyze_delay_causes_tool"
    ],
    "fallback_used": true,
    "validation_result": "deterministic_fallback"
  }
}
```

The `tools_called` chain shows the **agent choosing supporting evidence for a safety anomaly** — vendor analytics, safety alerts, then delay context.

---

## `POST /api/reports/executive-summary`

Returns the same `AgentResponse` shape, assembled in report mode from the month's strongest signals: top cross-domain concern, highest safety and billing risks, shift-readiness priority, a positive trend, and a data-quality note. Language stays conservative (e.g. *"potential billing irregularity warrants reconciliation review"*, never *"vendor committed fraud"*).
