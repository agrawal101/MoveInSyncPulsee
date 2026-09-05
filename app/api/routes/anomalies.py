from typing import Literal

from fastapi import APIRouter, Query

from app.analytics.anomaly_detection import detect_anomalies
from app.analytics.cross_domain_anomalies import detect_cross_domain_anomalies
from app.models.analytics import Anomaly, CrossDomainAnomaly, CrossDomainCategory

router = APIRouter(tags=["anomalies"])

MONTH = r"^\d{4}-\d{2}$"


def _as_anomaly(item: CrossDomainAnomaly) -> Anomaly:
    """Project a cross-domain anomaly onto the existing Anomaly contract.

    Lets ``/anomalies?include_cross_domain=true`` return one unified feed without
    breaking the current ``list[Anomaly]`` response the frontend already reads.
    """
    return Anomaly(
        id=item.id,
        category=item.category,
        entity_type=item.entity_type,
        entity_name=item.entity_name,
        metric="cross_signal_risk_score",
        current_value=item.cross_signal_risk_score,
        baseline_value=0.0,
        absolute_change=item.cross_signal_risk_score,
        relative_change_pct=None,
        # Cross-domain has no "positive"; low/medium/high map straight across.
        severity=item.severity,
        confidence=item.confidence,
        sample_size=item.sample_size,
        reason=item.why_flagged,
        supporting_dimensions={
            "title": item.title,
            "cross_domain": True,
            "signals": [s.model_dump() for s in item.signals],
            **item.supporting_dimensions,
        },
        data_quality_warnings=item.data_quality_warnings,
    )


@router.get("/anomalies", response_model=list[Anomaly])
def anomalies(
    month: str = Query(pattern=MONTH),
    severity: Literal["low", "medium", "high", "positive"] | None = None,
    limit: int = Query(10, ge=1, le=100),
    include_cross_domain: bool = Query(
        False, description="Append cross-domain anomalies, projected onto the Anomaly shape."
    ),
    baseline_month: str | None = Query(None, pattern=MONTH),
) -> list[Anomaly]:
    rows = detect_anomalies(month)
    if include_cross_domain:
        rows = rows + [
            _as_anomaly(item)
            for item in detect_cross_domain_anomalies(month, baseline_month)
        ]
        order = {"high": 0, "medium": 1, "positive": 2, "low": 3}
        rows.sort(key=lambda a: (order[a.severity], -abs(a.current_value)))
    return [row for row in rows if severity is None or row.severity == severity][:limit]


@router.get("/anomalies/cross-domain", response_model=list[CrossDomainAnomaly])
def cross_domain_anomalies(
    month: str = Query(pattern=MONTH),
    baseline_month: str | None = Query(None, pattern=MONTH),
    category: CrossDomainCategory | None = None,
    severity: Literal["low", "medium", "high"] | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> list[CrossDomainAnomaly]:
    rows = detect_cross_domain_anomalies(month, baseline_month)
    return [
        row
        for row in rows
        if (category is None or row.category == category)
        and (severity is None or row.severity == severity)
    ][:limit]
