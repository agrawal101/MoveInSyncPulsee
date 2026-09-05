from __future__ import annotations

import hashlib
from pathlib import Path

from app.analytics.service import AnalyticsService, compare_values
from app.models.analytics import Anomaly

MIN_VENDOR_TRIPS = 500
MIN_FEEDBACK_ROWS = 100


def classify_change(metric: str, current: float, baseline: float, sample_size: int) -> tuple[str | None, str]:
    """Apply explicit anomaly gates; return severity and confidence."""
    if sample_size < MIN_VENDOR_TRIPS:
        return None, "low"
    change = current - baseline
    relative = None if baseline == 0 else change / abs(baseline) * 100
    if metric in {"delay_rate", "no_show_rate"}:
        if change <= -0.02 and (relative is None or relative <= -20): return "positive", "high"
        if change >= 0.03 and relative is not None and relative >= 25: return "high", "high"
        if change >= 0.015 and relative is not None and relative >= 15: return "medium", "high"
    elif metric == "alerts_per_1000_trips":
        if change <= -5 and relative is not None and relative <= -20: return "positive", "high"
        if change >= 10 and relative is not None and relative >= 25: return "high", "high"
        if change >= 5 and relative is not None and relative >= 15: return "medium", "high"
    elif metric in {"average_billing", "cost_per_km"}:
        if current <= 0 or baseline <= 0: return None, "low"
        if relative is not None and relative <= -15: return "positive", "medium"
        if relative is not None and relative >= 25: return "high", "medium"
        if relative is not None and relative >= 15: return "medium", "medium"
    elif metric == "nonzero_rating" and sample_size >= MIN_FEEDBACK_ROWS:
        if change >= 0.20: return "positive", "medium"
        if change <= -0.30: return "high", "medium"
        if change <= -0.15: return "medium", "medium"
    return None, "high"


def _id(category: str, entity: str, metric: str, month: str) -> str:
    digest = hashlib.sha1(f"{category}|{entity}|{metric}|{month}".encode()).hexdigest()[:12]
    return f"anomaly-{digest}"


def detect_anomalies(month: str, database_path: Path = Path("data/processed/mobility.duckdb")) -> list[Anomaly]:
    service = AnalyticsService(database_path)
    baseline = service._previous_month(month)
    comparison = service.compare_vendor_performance(month, baseline)
    findings: list[Anomaly] = []
    for vendor in comparison.vendors:
        for metric_name in ("delay_rate", "alerts_per_1000_trips", "no_show_rate", "average_billing", "cost_per_km", "nonzero_rating"):
            metric = vendor.metrics[metric_name]
            if metric.current_value is None or metric.baseline_value is None:
                continue
            sample = int(metric.sample_size or 0)
            severity, confidence = classify_change(metric_name, float(metric.current_value), float(metric.baseline_value), sample)
            if not severity:
                continue
            absolute, relative = compare_values(metric.current_value, metric.baseline_value)
            direction = "improved" if severity == "positive" else "deteriorated"
            warnings = []
            if metric_name == "cost_per_km": warnings.append("Invalid/zero-distance bill rows excluded.")
            if metric_name == "nonzero_rating": warnings.append("Zero ratings excluded due ambiguous semantics.")
            findings.append(Anomaly(id=_id("vendor_performance", vendor.vendor, metric_name, month), category="vendor_performance", entity_type="vendor", entity_name=vendor.vendor, metric=metric_name, current_value=float(metric.current_value), baseline_value=float(metric.baseline_value), absolute_change=float(absolute or 0), relative_change_pct=relative, severity=severity, confidence=confidence, sample_size=sample, reason=f"{metric_name} {direction} versus {baseline} under deterministic threshold.", supporting_dimensions={"month": month, "baseline_month": baseline, "peer_rank": vendor.rank}, data_quality_warnings=warnings))
    eligible_shifts = [s for s in service.get_shift_readiness(month).shifts if s.get("pickup_sample", 0) >= 500]
    for shift in eligible_shifts[:10]:
        if shift.get("pickup_sample", 0) >= 500 and shift.get("risk_score", 0) >= 25:
            score = float(shift["risk_score"])
            findings.append(Anomaly(id=_id("shift_readiness", str(shift["shift_type"]), "risk_score", month), category="shift_readiness", entity_type="shift", entity_name=str(shift["shift_type"]), metric="risk_score", current_value=score, baseline_value=0.0, absolute_change=score, relative_change_pct=None, severity="high" if score >= 35 else "medium", confidence="high", sample_size=int(shift["rider_legs"]), reason="Composite risk exceeds deterministic threshold (25% late>5m, 45% late>10m, 30% no-show).", supporting_dimensions={k: shift.get(k) for k in ("late_5m_rate", "late_10m_rate", "no_show_rate", "offices", "vendors")}))
    overview = service.get_monthly_overview(month)
    no_show = overview.metrics["no_show_rate"]
    if no_show.previous_value is not None and no_show.current_value is not None:
        severity, confidence = classify_change("no_show_rate", float(no_show.current_value), float(no_show.previous_value), int(no_show.sample_size or 0))
        if severity == "positive":
            absolute, relative = compare_values(no_show.current_value, no_show.previous_value)
            findings.append(Anomaly(id=_id("mobility_overview", "fleet", "no_show_rate", month), category="mobility_overview", entity_type="fleet", entity_name="all", metric="no_show_rate", current_value=float(no_show.current_value), baseline_value=float(no_show.previous_value), absolute_change=float(absolute or 0), relative_change_pct=relative, severity="positive", confidence=confidence, sample_size=int(no_show.sample_size or 0), reason=f"Fleet no-show rate improved versus {baseline}."))
    order = {"high": 0, "medium": 1, "positive": 2, "low": 3}
    return sorted(findings, key=lambda item: (order[item.severity], -abs(item.relative_change_pct or item.absolute_change)))
