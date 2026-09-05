"""Deterministic cross-domain anomaly engine.

Correlates signals that already exist in the aggregate tables to surface
combinations that only become meaningful across domains (billing, safety,
service, shift, data quality). No raw records leave this module and no LLM is
consulted: detection is fully deterministic. The LLM layer only explains the
structured anomalies produced here.

Language policy: billing concerns are described as *potential* irregularities
that *require reconciliation review*. Nothing here asserts confirmed fraud.
"""

from __future__ import annotations

import hashlib
import statistics
from pathlib import Path
from typing import Any

import duckdb

from app.models.analytics import (
    CrossDomainAnomaly,
    CrossDomainSignal,
    RiskComponent,
)

DB_DEFAULT = Path("data/processed/mobility.duckdb")

# --- Deterministic thresholds (calibrated against real 2026 data) ------------
MIN_VENDOR_TRIPS = 500          # sample-size protection for vendor signals
MIN_SHIFT_SAMPLE = 500          # sample-size protection for shift signals
MIN_BILL_ROWS = 500             # scale gate for data-integrity anomalies

MATERIAL_BILLING_PCT = 5.0      # billing move considered material
STABLE_BAND_PCT = 4.0           # |volume change| below this reads as "stable"
BILLING_TRIP_DIVERGENCE = 4.0   # billing outgrows trips by >= this (pp)
LOW_COVERAGE_PCT = 60.0         # valid-distance coverage below this is weak
HIGH_ZERO_DIST_PCT = 40.0       # zero-distance billing concentration
SEVERE_ZERO_DIST_PCT = 90.0     # near-total zero-distance billing

NO_SHOW_MATERIAL = 0.015
ALERT_RATE_MATERIAL = 5.0       # per-1000-trips absolute move
ALERT_RATE_HIGH = 10.0
ALERT_REL_MATERIAL = 15.0       # per-1000-trips relative move (%)
DELAY_MATERIAL = 0.015
RATING_DROP_MATERIAL = 0.15
UTIL_DROP_MATERIAL = 0.02
CPK_PEER_MULTIPLE = 1.25        # cost/km vs peer median

# Shift readiness reuses the existing composite risk weighting.
SHIFT_RISK_FLAG = 28.0          # composite risk gate (0.25*late5+0.45*late10+0.30*nsr)
SHIFT_ABNORMAL_LATE10 = 0.30    # absolute late-10m gate for the peer-outlier path


def _rows(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _rel(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline in (None, 0):
        return None
    return round((float(current) - float(baseline)) / abs(float(baseline)) * 100, 2)


def _diff(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return round(float(current) - float(baseline), 4)


def _median(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(statistics.median(clean), 4) if clean else None


def _round(value: Any, digits: int = 4) -> Any:
    return round(float(value), digits) if isinstance(value, (int, float)) else value


def _id(category: str, entity: str, month: str) -> str:
    digest = hashlib.sha1(f"{category}|{entity}|{month}".encode()).hexdigest()[:12]
    return f"cross-{digest}"


def _change_signal(
    metric: str, change: float | None, direction: str, weight: float,
    note: str, rel: float | None = None,
) -> CrossDomainSignal:
    """A *_change signal carries the delta as current_value (baseline is zero)."""
    return CrossDomainSignal(
        metric=metric, current_value=_round(change, 4), baseline_value=0.0,
        relative_change_pct=rel, direction=direction, weight=weight, note=note)


class CrossDomainAnomalyEngine:
    def __init__(self, database_path: Path = DB_DEFAULT) -> None:
        self.database_path = database_path

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if not self.database_path.exists():
            raise FileNotFoundError(f"DuckDB not found: {self.database_path}")
        return duckdb.connect(str(self.database_path), read_only=True)

    def _months(self, c: duckdb.DuckDBPyConnection) -> list[str]:
        return [r[0] for r in c.execute(
            "SELECT month FROM monthly_metrics ORDER BY month"
        ).fetchall()]

    # -- Signal assembly ------------------------------------------------------
    def build_vendor_signals(
        self, month: str, baseline_month: str | None
    ) -> list[dict[str, Any]]:
        """Assemble a per-vendor cross-domain feature record from aggregates."""
        with self._connect() as c:
            months = self._months(c)
            if month not in months:
                raise ValueError(f"Unknown month: {month}")
            if baseline_month is None:
                idx = months.index(month)
                baseline_month = months[idx - 1] if idx else None
            if baseline_month is not None and baseline_month not in months:
                raise ValueError(f"Unknown baseline month: {baseline_month}")

            cur = {r["vendor"]: r for r in _rows(c.execute(
                "SELECT * FROM vendor_monthly_metrics WHERE month=?", [month]))}
            base = {r["vendor"]: r for r in _rows(c.execute(
                "SELECT * FROM vendor_monthly_metrics WHERE month=?",
                [baseline_month]))} if baseline_month else {}

            # Bill-quality signals from the raw bill quality flags (current month).
            billq = {r["vendor"]: r for r in _rows(c.execute(
                """SELECT vendor, count(*) bill_rows,
                          sum(CASE WHEN q_zero_distance THEN 1 ELSE 0 END) zero_dist,
                          sum(CASE WHEN q_negative_distance THEN 1 ELSE 0 END) neg_dist,
                          sum(CASE WHEN NOT EXISTS(
                              SELECT 1 FROM rides r
                              WHERE r.month=b.month AND r.trip_id=b.trip_id
                          ) THEN 1 ELSE 0 END) missing_join
                   FROM bills b WHERE month=? GROUP BY vendor""", [month]))}

            # Utilization + travelled distance from rides (current + baseline).
            def util(m: str) -> dict[str, dict[str, Any]]:
                return {r["vendor"]: r for r in _rows(c.execute(
                    """SELECT vendor_id vendor,
                              sum(actualemployee_cnt) act_pax,
                              sum(actual_cab_capacity) cap,
                              sum(traveled_km) trav_km,
                              sum(planned_km) plan_km
                       FROM rides WHERE month=? GROUP BY vendor_id""", [m]))}
            util_cur, util_base = util(month), util(baseline_month) if baseline_month else {}

        signals: list[dict[str, Any]] = []
        for vendor, row in cur.items():
            b = base.get(vendor, {})
            uc, ub = util_cur.get(vendor, {}), util_base.get(vendor, {})
            bq = billq.get(vendor, {})
            trips = int(row.get("trips") or 0)
            bill_rows = int(row.get("bill_rows") or 0)
            valid_rows = int(row.get("valid_distance_rows") or 0)

            def util_of(u: dict[str, Any]) -> float | None:
                pax, cap = u.get("act_pax"), u.get("cap")
                return round(pax / cap, 4) if pax and cap else None

            zero_dist = int(bq.get("zero_dist") or 0)
            signals.append({
                "vendor": vendor,
                "trips": trips,
                "trip_volume_change_pct": _rel(row.get("trips"), b.get("trips")),
                "total_cost": _round(row.get("total_billing"), 2),
                "billing_change_pct": _rel(row.get("total_billing"), b.get("total_billing")),
                "cost_per_valid_km": _round(row.get("cost_per_km"), 2),
                "cost_per_valid_km_change": _rel(row.get("cost_per_km"), b.get("cost_per_km")),
                "valid_cost_km_coverage": round(100 * valid_rows / bill_rows, 2) if bill_rows else None,
                "no_show_rate": _round(row.get("no_show_rate")),
                "no_show_change": _diff(row.get("no_show_rate"), b.get("no_show_rate")),
                "delay_rate": _round(row.get("delay_rate")),
                "delay_rate_change": _diff(row.get("delay_rate"), b.get("delay_rate")),
                "average_delay": _round(row.get("avg_delay_minutes"), 2),
                "safety_alerts_per_1000_trips": _round(row.get("alerts_per_1000_trips"), 2),
                "safety_alert_rate_change": _diff(row.get("alerts_per_1000_trips"), b.get("alerts_per_1000_trips")),
                "safety_alert_rate_rel": _rel(row.get("alerts_per_1000_trips"), b.get("alerts_per_1000_trips")),
                "experience_rating": _round(row.get("nonzero_rating"), 2),
                "experience_rating_change": _diff(row.get("nonzero_rating"), b.get("nonzero_rating")),
                "utilization": util_of(uc),
                "utilization_change": _diff(util_of(uc), util_of(ub)),
                "zero_distance_billing_rate": round(100 * zero_dist / bill_rows, 2) if bill_rows else None,
                "negative_distance_count": int(bq.get("neg_dist") or 0),
                "missing_join_count": int(bq.get("missing_join") or 0),
                "bill_rows": bill_rows,
                "peer_rank": None,
            })

        # Peer medians across eligible vendors for peer benchmarking.
        eligible = [s for s in signals if s["trips"] >= MIN_VENDOR_TRIPS]
        peers = {
            "cost_per_valid_km": _median([s["cost_per_valid_km"] for s in eligible]),
            "safety_alerts_per_1000_trips": _median([s["safety_alerts_per_1000_trips"] for s in eligible]),
            "no_show_rate": _median([s["no_show_rate"] for s in eligible]),
            "delay_rate": _median([s["delay_rate"] for s in eligible]),
            "zero_distance_billing_rate": _median([s["zero_distance_billing_rate"] for s in eligible]),
        }
        for s in signals:
            s["_peers"] = peers
            s["_baseline_month"] = baseline_month
            s["_month"] = month
        return signals

    def build_shift_signals(self, month: str) -> list[dict[str, Any]]:
        with self._connect() as c:
            if month not in self._months(c):
                raise ValueError(f"Unknown month: {month}")
            rows = _rows(c.execute(
                """SELECT *, late_5m::DOUBLE/nullif(pickup_sample,0) late5,
                          late_10m::DOUBLE/nullif(pickup_sample,0) late10,
                          no_shows::DOUBLE/nullif(rider_legs,0) nsr,
                          round(100*(0.25*late_5m::DOUBLE/nullif(pickup_sample,0)
                                    +0.45*late_10m::DOUBLE/nullif(pickup_sample,0)
                                    +0.30*no_shows::DOUBLE/nullif(rider_legs,0)),2) risk_score
                   FROM shift_monthly_metrics WHERE month=?""", [month]))
        return [r for r in rows if (r.get("pickup_sample") or 0) >= MIN_SHIFT_SAMPLE]

    # -- Scoring --------------------------------------------------------------
    @staticmethod
    def _score(
        signals: list[CrossDomainSignal],
        peer_points: float,
        peer_detail: str,
        sample_size: int,
        coverage_conf: float,
        conf_detail: str,
    ) -> tuple[float, list[RiskComponent]]:
        """Explainable additive score in [0, 100]. Never a fraud probability."""
        historical = min(45.0, round(sum(s.weight for s in signals), 2))
        abnormal = [s for s in signals if s.direction in ("worse", "better")]
        correlation = min(20.0, max(0, len(abnormal) - 1) * 8.0)
        peer = min(25.0, round(peer_points, 2))
        confidence = min(10.0, round(coverage_conf, 2))
        total = round(min(100.0, historical + correlation + peer + confidence), 1)
        components = [
            RiskComponent(name="historical_deviation", value=historical,
                          detail="Weighted magnitude of signals moving versus baseline."),
            RiskComponent(name="correlated_signals", value=correlation,
                          detail=f"{len(abnormal)} signals moved together across domains."),
            RiskComponent(name="peer_deviation", value=peer, detail=peer_detail),
            RiskComponent(name="data_confidence", value=confidence, detail=conf_detail),
        ]
        return total, components

    @staticmethod
    def _severity(score: float) -> str:
        return "high" if score >= 70 else "medium" if score >= 45 else "low"

    @staticmethod
    def _confidence(sample_size: int, coverage: float | None) -> str:
        if sample_size >= 3000 and (coverage is None or coverage >= LOW_COVERAGE_PCT):
            return "high"
        if sample_size >= MIN_VENDOR_TRIPS:
            return "medium"
        return "low"

    # -- Detectors ------------------------------------------------------------
    def _billing_integrity(self, s: dict[str, Any]) -> CrossDomainAnomaly | None:
        bill_chg = s["billing_change_pct"]
        trip_chg = s["trip_volume_change_pct"]
        coverage = s["valid_cost_km_coverage"]
        cpk = s["cost_per_valid_km"]
        peer_cpk = s["_peers"].get("cost_per_valid_km")
        signals: list[CrossDomainSignal] = []
        reasons: list[str] = []

        billing_up = bill_chg is not None and bill_chg >= MATERIAL_BILLING_PCT
        trip_stable = trip_chg is not None and abs(trip_chg) < STABLE_BAND_PCT
        divergence = (
            bill_chg is not None and trip_chg is not None
            and bill_chg - trip_chg >= BILLING_TRIP_DIVERGENCE
        )
        low_coverage = coverage is not None and coverage < LOW_COVERAGE_PCT
        cpk_vs_peer = (
            cpk is not None and peer_cpk not in (None, 0)
            and cpk >= peer_cpk * CPK_PEER_MULTIPLE
        )

        if not (billing_up and (low_coverage or divergence or cpk_vs_peer)):
            return None

        signals.append(_change_signal(
            "billing_change_pct", bill_chg, "worse", 20.0,
            "Total billing rose versus baseline.", rel=bill_chg))
        if divergence:
            signals.append(_change_signal(
                "trip_volume_change_pct", trip_chg,
                "worse" if not trip_stable else "stable", 12.0,
                "Billing outgrew trip volume.", rel=trip_chg))
            reasons.append("faster than trip volume grew")
        elif trip_stable:
            signals.append(_change_signal(
                "trip_volume_change_pct", trip_chg, "stable", 6.0,
                "Trip volume broadly stable.", rel=trip_chg))
            reasons.append("while trip volume stayed broadly stable")
        if low_coverage:
            signals.append(CrossDomainSignal(
                metric="valid_cost_km_coverage", current_value=coverage,
                direction="worse", weight=15.0,
                note="Few bill rows carry valid distance to reconcile cost."))
            reasons.append("but valid travelled-distance coverage is too low to reconcile cost")
        if cpk_vs_peer:
            signals.append(CrossDomainSignal(
                metric="cost_per_valid_km", current_value=cpk, peer_median=peer_cpk,
                direction="worse", weight=12.0,
                note="Cost per valid km sits above the peer median."))
            reasons.append("with cost per valid kilometre high relative to peers")
        # Correlated demand-side context that strengthens the case.
        if s["no_show_change"] is not None and s["no_show_change"] >= NO_SHOW_MATERIAL:
            signals.append(_change_signal(
                "no_show_change", s["no_show_change"], "worse", 8.0,
                "No-shows rose alongside billing."))
            reasons.append("as no-shows increased")
        util_chg = s["utilization_change"]
        if util_chg is not None and util_chg <= -UTIL_DROP_MATERIAL:
            signals.append(_change_signal(
                "utilization_change", util_chg, "worse", 8.0,
                "Passenger utilization fell."))
            reasons.append("while passenger utilization declined")

        peer_points = 15.0 if cpk_vs_peer else 6.0 if low_coverage else 0.0
        cov_conf = 3.0 if low_coverage else 8.0
        score, comps = self._score(
            signals, peer_points,
            "Cost per valid km vs peer median." if cpk_vs_peer else "Coverage limits peer comparison.",
            s["trips"],
            cov_conf,
            "Large billing sample; low distance coverage limits cost reconciliation."
            if low_coverage else "Adequate coverage for cost comparison.",
        )
        warnings = []
        if low_coverage:
            warnings.append("Valid travelled-distance coverage is low; cost/km is not reliably reconcilable.")
        return CrossDomainAnomaly(
            id=_id("billing_integrity", s["vendor"], s["_month"]),
            category="billing_integrity", entity_type="vendor", entity_name=s["vendor"],
            title="Potential billing irregularity",
            severity=self._severity(score),
            confidence=self._confidence(s["trips"], coverage),
            cross_signal_risk_score=score, signals=signals,
            why_flagged=(
                "Billing rose materially " + " ".join(reasons)
                + ". This combination requires billing reconciliation review; it is a potential "
                "irregularity to investigate, not a confirmed finding."),
            recommended_investigation=[
                "Reconcile invoiced trips against travelled-distance and trip records for the vendor.",
                "Confirm whether zero/low-distance bill rows are legitimate fixed-slab trips or data gaps.",
                "Compare cost per valid kilometre against peer vendors on the same contracts.",
                "Verify no-show and utilization trends do not inflate per-trip billing.",
            ],
            risk_components=comps, sample_size=s["trips"],
            month=s["_month"], baseline_month=s["_baseline_month"],
            supporting_dimensions={"peer_rank": s.get("peer_rank"),
                                   "zero_distance_billing_rate": s["zero_distance_billing_rate"]},
            data_quality_warnings=warnings,
        )

    def _safety_pattern(self, s: dict[str, Any]) -> CrossDomainAnomaly | None:
        alr_chg = s["safety_alert_rate_change"]
        alr_rel = s["safety_alert_rate_rel"]
        worse_safety = (
            alr_chg is not None and alr_chg >= ALERT_RATE_MATERIAL
            and (alr_rel is None or alr_rel >= ALERT_REL_MATERIAL)
        )
        if not worse_safety:
            return None
        no_show_chg = s["no_show_change"]
        delay_chg = s["delay_rate_change"]
        # Divergence: safety worsens while service metrics improve or hold.
        service_ok = (
            (no_show_chg is None or no_show_chg <= NO_SHOW_MATERIAL)
            and (delay_chg is None or delay_chg <= DELAY_MATERIAL)
        )
        if not service_ok:
            return None
        weight = 25.0 if alr_chg >= ALERT_RATE_HIGH else 16.0
        signals = [_change_signal(
            "safety_alert_rate_change", alr_chg, "worse", weight,
            "Safety alert frequency rose materially.", rel=alr_rel)]
        if no_show_chg is not None and no_show_chg < 0:
            signals.append(_change_signal(
                "no_show_change", no_show_chg, "better", 6.0,
                "No-show performance improved."))
        if delay_chg is not None and delay_chg < 0:
            signals.append(_change_signal(
                "delay_rate_change", delay_chg, "better", 6.0,
                "Delay performance improved."))
        peer_alr = s["_peers"].get("safety_alerts_per_1000_trips")
        peer_points = 0.0
        if peer_alr and s["safety_alerts_per_1000_trips"] and s["safety_alerts_per_1000_trips"] >= peer_alr * 1.25:
            peer_points = 18.0
            signals.append(CrossDomainSignal(
                metric="safety_alerts_per_1000_trips",
                current_value=s["safety_alerts_per_1000_trips"], peer_median=peer_alr,
                direction="worse", weight=10.0, note="Alert rate exceeds peer median."))
        score, comps = self._score(
            signals, peer_points, "Alert rate vs peer median.", s["trips"], 8.0,
            "Vendor trip sample supports the safety comparison.")
        return CrossDomainAnomaly(
            id=_id("safety_pattern", s["vendor"], s["_month"]),
            category="safety_pattern", entity_type="vendor", entity_name=s["vendor"],
            title="Safety divergence", severity=self._severity(score),
            confidence=self._confidence(s["trips"], None),
            cross_signal_risk_score=score, signals=signals,
            why_flagged=(
                "Safety alert frequency increased materially despite steady or improving delay and "
                "no-show performance, indicating a safety-specific deterioration rather than broad "
                "service decline."),
            recommended_investigation=[
                "Break the alert increase down by alert type, office, and repeated vehicle.",
                "Confirm acknowledgement times and whether alerts cluster in specific windows.",
                "Keep improving delay/no-show trends separate from the safety concern.",
            ],
            risk_components=comps, sample_size=s["trips"],
            month=s["_month"], baseline_month=s["_baseline_month"],
            supporting_dimensions={"peer_rank": s.get("peer_rank")},
        )

    def _vendor_divergence(self, s: dict[str, Any]) -> CrossDomainAnomaly | None:
        """One non-safety service dimension deteriorates while others hold/improve."""
        candidates: list[tuple[str, CrossDomainSignal, str]] = []
        delay_chg = s["delay_rate_change"]
        if delay_chg is not None and delay_chg >= DELAY_MATERIAL:
            candidates.append(("delay_rate_change", _change_signal(
                "delay_rate_change", delay_chg, "worse", 18.0,
                "Delay rate deteriorated."), "delay rate"))
        ns_chg = s["no_show_change"]
        if ns_chg is not None and ns_chg >= NO_SHOW_MATERIAL:
            candidates.append(("no_show_change", _change_signal(
                "no_show_change", ns_chg, "worse", 18.0,
                "No-show rate deteriorated."), "no-show rate"))
        rating_chg = s["experience_rating_change"]
        if rating_chg is not None and rating_chg <= -RATING_DROP_MATERIAL:
            candidates.append(("experience_rating_change", _change_signal(
                "experience_rating_change", rating_chg, "worse", 16.0,
                "Experience rating dropped."), "experience rating"))
        util_chg = s["utilization_change"]
        if util_chg is not None and util_chg <= -UTIL_DROP_MATERIAL:
            candidates.append(("utilization_change", _change_signal(
                "utilization_change", util_chg, "worse", 14.0,
                "Utilization declined."), "passenger utilization"))
        if not candidates:
            return None
        # Require the rest of the profile to be broadly stable/improving, so this
        # is a genuine single-dimension divergence rather than broad decline.
        deteriorating = len(candidates)
        alr_chg = s["safety_alert_rate_change"]
        if alr_chg is not None and alr_chg >= ALERT_RATE_MATERIAL:
            # A safety spike belongs to the safety detector; skip to avoid double-count.
            return None
        if deteriorating > 2:
            return None
        signals = [c[1] for c in candidates]
        # Add up to one improving counter-signal to show divergence.
        for metric, chg, better in (
            ("delay_rate_change", s["delay_rate_change"], "delay"),
            ("no_show_change", s["no_show_change"], "no-show"),
        ):
            if chg is not None and chg < 0 and metric not in {c[0] for c in candidates}:
                signals.append(_change_signal(
                    metric, chg, "better", 5.0, f"{better.title()} improved."))
                break
        score, comps = self._score(
            signals, 0.0, "No peer comparison applied.", s["trips"], 8.0,
            "Vendor trip sample supports the comparison.")
        dims = _join_reasons([c[2] for c in candidates])
        return CrossDomainAnomaly(
            id=_id("vendor_operational_divergence", s["vendor"], s["_month"]),
            category="vendor_operational_divergence", entity_type="vendor",
            entity_name=s["vendor"], title="Vendor operational divergence",
            severity=self._severity(score),
            confidence=self._confidence(s["trips"], None),
            cross_signal_risk_score=score, signals=signals,
            why_flagged=(
                f"The vendor's {dims} deteriorated materially while other service dimensions stayed "
                "stable or improved, isolating a specific operational issue rather than broad decline."),
            recommended_investigation=[
                "Review the deteriorating dimension against route, office, and shift breakdowns.",
                "Confirm the divergence is not driven by a small number of affected trips.",
                "Compare the vendor's trajectory with peers on the same contracts.",
            ],
            risk_components=comps, sample_size=s["trips"],
            month=s["_month"], baseline_month=s["_baseline_month"],
            supporting_dimensions={"peer_rank": s.get("peer_rank")},
        )

    def _data_integrity(self, s: dict[str, Any]) -> CrossDomainAnomaly | None:
        zero_pct = s["zero_distance_billing_rate"]
        bill_rows = s["bill_rows"]
        neg = s["negative_distance_count"]
        if bill_rows < MIN_BILL_ROWS:
            return None
        triggered = (zero_pct is not None and zero_pct >= HIGH_ZERO_DIST_PCT) or neg > 0
        if not triggered:
            return None
        signals: list[CrossDomainSignal] = []
        reasons: list[str] = []
        peer_zero = s["_peers"].get("zero_distance_billing_rate")
        if zero_pct is not None and zero_pct >= HIGH_ZERO_DIST_PCT:
            weight = 30.0 if zero_pct >= SEVERE_ZERO_DIST_PCT else 18.0
            signals.append(CrossDomainSignal(
                metric="zero_distance_billing_rate", current_value=zero_pct,
                peer_median=peer_zero, direction="worse", weight=weight,
                note="Large share of bills carry zero travelled distance."))
            reasons.append("a large share of bills carry zero travelled distance")
        if neg > 0:
            signals.append(CrossDomainSignal(
                metric="negative_distance_count", current_value=neg,
                direction="worse", weight=12.0, note="Negative distances present in billing."))
            reasons.append("negative travelled distances appear in billing")
        if s["missing_join_count"] and s["missing_join_count"] > 0:
            signals.append(CrossDomainSignal(
                metric="missing_join_count", current_value=s["missing_join_count"],
                direction="worse", weight=6.0, note="Bill rows without a matching trip."))
            reasons.append("some bill rows have no matching trip record")
        peer_points = 0.0
        if peer_zero not in (None, 0) and zero_pct and zero_pct >= peer_zero * 1.25:
            peer_points = 15.0
        score, comps = self._score(
            signals, peer_points, "Zero-distance rate vs peer median.",
            bill_rows, 8.0, "Large bill sample makes the pattern reliable.")
        return CrossDomainAnomaly(
            id=_id("data_integrity_anomaly", s["vendor"], s["_month"]),
            category="data_integrity_anomaly", entity_type="vendor",
            entity_name=s["vendor"], title="Billing data-integrity concentration",
            severity=self._severity(score),
            confidence="high" if bill_rows >= 3000 else "medium",
            cross_signal_risk_score=score, signals=signals,
            why_flagged=(
                "Billing quality is compromised because " + _join_reasons(reasons)
                + ". At this scale it materially blocks cost reconciliation and requires review."),
            recommended_investigation=[
                "Determine whether zero-distance bills are valid fixed-slab trips or missing distance capture.",
                "Trace a sample of affected bill rows back to source trip and GPS records.",
                "Exclude unreconcilable rows from cost/km reporting until resolved.",
            ],
            risk_components=comps, sample_size=bill_rows,
            month=s["_month"], baseline_month=s["_baseline_month"],
            supporting_dimensions={"bill_rows": bill_rows,
                                   "valid_cost_km_coverage": s["valid_cost_km_coverage"]},
            data_quality_warnings=[
                "Zero-distance bill rows are excluded from normalized cost metrics."],
        )

    def _shift_pattern(self, shift: dict[str, Any], peer_late10: float | None
                       ) -> CrossDomainAnomaly | None:
        risk = float(shift.get("risk_score") or 0)
        late10 = shift.get("late10")
        abnormal_vs_peer = (
            peer_late10 is not None and late10 is not None
            and late10 >= peer_late10 * 1.5 and late10 >= SHIFT_ABNORMAL_LATE10
        )
        if risk < SHIFT_RISK_FLAG and not abnormal_vs_peer:
            return None
        sample = int(shift.get("pickup_sample") or 0)
        signals = [
            CrossDomainSignal(metric="late_10m_rate", current_value=_round(late10),
                              peer_median=peer_late10, direction="worse", weight=20.0,
                              note="Late-beyond-10-minute pickups are high."),
            CrossDomainSignal(metric="late_5m_rate", current_value=_round(shift.get("late5")),
                              direction="worse", weight=10.0,
                              note="Late-beyond-5-minute pickups are high."),
        ]
        nsr = shift.get("nsr")
        if nsr is not None and nsr >= 0.05:
            signals.append(CrossDomainSignal(
                metric="no_show_rate", current_value=_round(nsr),
                direction="worse", weight=8.0, note="No-show rate is elevated."))
        peer_points = 18.0 if abnormal_vs_peer else 6.0
        score, comps = self._score(
            signals, peer_points, "Late-pickup rate vs peer shift median.",
            sample, 8.0, "Pickup sample supports the shift comparison.")
        vendors = int(shift.get("vendors") or 0)
        return CrossDomainAnomaly(
            id=_id("shift_readiness_pattern", str(shift["shift_type"]), shift["month"]),
            category="shift_readiness_pattern", entity_type="shift",
            entity_name=str(shift["shift_type"]),
            title="Shift readiness pattern", severity=self._severity(score),
            confidence="high" if sample >= 3000 else "medium",
            cross_signal_risk_score=score, signals=signals,
            why_flagged=(
                "This shift's pickup lateness is abnormally high relative to other shifts, spanning "
                "multiple offices and vendors, marking a readiness gap rather than an isolated route."),
            recommended_investigation=[
                "Identify which offices and vendors concentrate the late pickups in this shift.",
                "Check cab positioning and roster coverage ahead of this shift window.",
                "Compare against the same shift in prior months to confirm persistence.",
            ],
            risk_components=comps, sample_size=sample,
            month=shift["month"], baseline_month=None,
            supporting_dimensions={"offices": shift.get("offices"), "vendors": vendors,
                                   "risk_score": risk},
        )

    # -- Orchestration --------------------------------------------------------
    def detect(self, month: str, baseline_month: str | None = None
               ) -> list[CrossDomainAnomaly]:
        vendor_signals = self.build_vendor_signals(month, baseline_month)
        eligible = [s for s in vendor_signals if s["trips"] >= MIN_VENDOR_TRIPS]
        found: list[CrossDomainAnomaly] = []
        for s in eligible:
            for detector in (
                self._billing_integrity, self._safety_pattern,
                self._vendor_divergence, self._data_integrity,
            ):
                anomaly = detector(s)
                if anomaly is not None:
                    found.append(anomaly)
        shifts = self.build_shift_signals(month)
        peer_late10 = _median([sh.get("late10") for sh in shifts])
        for sh in shifts:
            anomaly = self._shift_pattern(sh, peer_late10)
            if anomaly is not None:
                found.append(anomaly)
        rank = {"high": 0, "medium": 1, "low": 2}
        found.sort(key=lambda a: (rank[a.severity], -a.cross_signal_risk_score))
        return found


def _join_reasons(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return "shows a suspicious combination of signals"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def detect_cross_domain_anomalies(
    month: str,
    baseline_month: str | None = None,
    database_path: Path = DB_DEFAULT,
) -> list[CrossDomainAnomaly]:
    """Deterministically correlate multi-domain signals into prioritized anomalies."""
    return CrossDomainAnomalyEngine(database_path).detect(month, baseline_month)
