# Cross-Domain Anomaly Methodology

## The key innovation

A metric can look perfectly normal in isolation. The valuable anomalies are **suspicious combinations of signals that only become meaningful when data from multiple domains is combined.**

**Traditional approach — one dashboard, one domain:**

```
Billing dashboard  → billing anomalies
Safety dashboard   → safety anomalies
Trip dashboard     → delay anomalies
```

Each dashboard is blind to the others, so cross-signal patterns fall through the gaps.

**Pulse approach — correlate across domains:**

```
Trips + Safety + Billing + Employee + Experience
                     ↓
            Cross-signal anomaly
```

Implemented deterministically in [`app/analytics/cross_domain_anomalies.py`](../../app/analytics/cross_domain_anomalies.py). No raw data is sent to an LLM; detection is pure SQL/Python.

---

## Supported categories

| Category | What it correlates | Real July example |
|---|---|---|
| **billing_integrity** | billing change vs trip growth, valid-distance coverage, cost/km vs peers, no-show, utilization | Aarav Petrov: billing rose while valid-distance coverage was too low to reconcile cost |
| **safety_pattern** | alert rate change vs baseline, alert rate vs peers, delay & no-show direction | Aarav Petrov: safety alerts up sharply **while** delay & no-show improved |
| **vendor_operational_divergence** | one service dimension (delay / no-show / rating / utilization) deteriorating while the rest hold | Meera Pavlov: delay & rating down while no-show improved |
| **shift_readiness_pattern** | late-5m, late-10m, no-show vs peer shifts and composite risk | Shifts 06:30 and 13:00: high late-pickup across many offices/vendors |
| **data_integrity_anomaly** | zero-distance billing concentration, negative distance, missing joins, at scale | Sneha / Meera Pavlov ≈100% zero-distance bills |

---

## Signal model (vendor)

Derived only from columns that exist in the real dataset:

`trip_count`, `trip_volume_change_pct`, `total_cost`, `billing_change_pct`, `cost_per_valid_km` (+ change), `valid_cost_km_coverage`, `no_show_rate` (+ change), `delay_rate` (+ change), `average_delay`, `safety_alerts_per_1000_trips` (+ change), `experience_rating` (+ change), `utilization` (+ change), `zero_distance_billing_rate`, `negative_distance_count`, `missing_join_count`, `bill_rows`.

Unavailable fields are left null — no invented columns.

---

## Benchmarking

1. **Historical** — current month vs a baseline month (default = previous available month; the API also accepts an explicit `baseline_month`). Each signal carries `baseline_value` and, where meaningful, `relative_change_pct`.
2. **Peer** — the entity vs the median of *eligible* peers (vendors with ≥ `MIN_VENDOR_TRIPS` trips; shifts vs other eligible shifts). Signals carry `peer_median`.
3. **Absolute magnitude** — thresholds are expressed in real units (percentage points, per-1000-trips, coverage %).
4. **Sample size** — every anomaly reports `sample_size`.

---

## Sample-size protection

Vendors below `MIN_VENDOR_TRIPS` (500) and shifts below `MIN_SHIFT_SAMPLE` (500) are excluded. Data-integrity anomalies require `MIN_BILL_ROWS` (500) so a high rate on a tiny denominator cannot masquerade as a systemic issue. This is exactly why noisy small-sample outliers don't reach the priority feed.

---

## Thresholds (deterministic, calibrated on real 2026 data)

| Signal | Materiality gate |
|---|---|
| Billing change | ≥ 5% |
| Trip-stable band | \|change\| < 4pp |
| Billing/trip divergence | ≥ 4pp |
| Valid-distance coverage (low) | < 60% |
| Zero-distance billing concentration | ≥ 40% (severe ≥ 90%) |
| No-show change | ≥ 0.015 |
| Safety alert rate change | ≥ +5/1000 (high ≥ +10) and ≥ 15% relative |
| Delay-rate change | ≥ 0.015 |
| Rating drop | ≥ 0.15 |
| Utilization drop | ≥ 0.02 |
| Cost/km vs peer | ≥ 1.25× peer median |
| Shift composite risk | ≥ 28, or late-10m ≥ 0.30 vs peers |

Thresholds live as named constants at the top of the engine module and are unit-tested.

---

## `cross_signal_risk_score` — explainable, not a black box

A prioritization score in **[0, 100]**, additive and fully decomposed (no ML model):

```
cross_signal_risk_score =
      historical_deviation   (Σ signal weights, capped 45)
    + correlated_signals     ((n_abnormal − 1) × 8, capped 20)
    + peer_deviation         (capped 25)
    + data_confidence        (capped 10)
```

Every anomaly returns `risk_components[]` with the value and a plain-English `detail` for each term, so a reviewer can see *why* a score is what it is. A test asserts the score equals the (capped) sum of its published components.

---

## Conservative terminology — "potential", never "proven"

Billing findings are surfaced as **potential billing irregularities that require reconciliation review**. This deliberately does **not** mean fraud is proven.

- Titles/why-text use: *potential billing irregularity*, *requires billing reconciliation review*, *reconciliation anomaly*, *requires investigation*.
- The engine, agent prompt, and deterministic fallback all avoid asserting fraud; automated tests scan output for banned phrases (`"fraud detected"`, `"confirmed fraud"`, …) and fail if any appear.
- Fraud may only be framed as a **possible risk to investigate**, never a finding.
