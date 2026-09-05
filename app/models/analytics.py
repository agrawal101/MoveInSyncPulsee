from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DataQualityWarning(BaseModel):
    code: str
    message: str
    affected_rows: int | None = None


class MetricComparison(BaseModel):
    metric: str
    current_value: float | int | None
    previous_value: float | int | None = None
    baseline_value: float | int | None = None
    absolute_change: float | None = None
    relative_change_pct: float | None = None
    unit: str
    sample_size: int | None = None
    confidence: Literal["high", "medium", "low"] = "high"
    warnings: list[DataQualityWarning] = Field(default_factory=list)


class MonthlyOverview(BaseModel):
    month: str
    previous_month: str | None
    baseline_month: str | None
    metrics: dict[str, MetricComparison]
    data_quality_warnings: list[DataQualityWarning] = Field(default_factory=list)


class VendorResult(BaseModel):
    vendor: str
    month: str
    rank: int | None = None
    metrics: dict[str, MetricComparison]
    deterioration_score: float = 0.0
    data_quality_warnings: list[DataQualityWarning] = Field(default_factory=list)


class VendorAnalysis(BaseModel):
    current_month: str
    baseline_month: str | None
    vendors: list[VendorResult]


class ShiftReadiness(BaseModel):
    month: str
    shifts: list[dict[str, Any]]
    data_quality_warnings: list[DataQualityWarning] = Field(default_factory=list)


class SafetyAnalysis(BaseModel):
    month: str
    filters: dict[str, str | None]
    alert_count: int
    trip_count: int
    alerts_per_1000_trips: float | None
    severity_distribution: list[dict[str, Any]]
    alert_type_distribution: list[dict[str, Any]]
    vendor_concentration: list[dict[str, Any]]
    office_concentration: list[dict[str, Any]]
    acknowledgement_minutes: dict[str, float | int | None]
    repeated_vehicle_patterns: list[dict[str, Any]]
    data_quality_warnings: list[DataQualityWarning] = Field(default_factory=list)


class CostAnalysis(BaseModel):
    month: str
    vendor: str | None
    billed_rows: int
    total_billing_amount: float | None
    average_billing_amount: float | None
    valid_distance_rows: int
    excluded_distance_rows: int
    distance_metric_coverage_pct: float
    total_valid_distance_km: float | None
    cost_per_km: float | None
    data_quality_warnings: list[DataQualityWarning] = Field(default_factory=list)


class ExperienceAnalysis(BaseModel):
    month: str
    vendor: str | None
    feedback_rows: int
    dimensions: dict[str, dict[str, float | int | None]]
    data_quality_warnings: list[DataQualityWarning] = Field(default_factory=list)


class Anomaly(BaseModel):
    id: str
    category: str
    entity_type: str
    entity_name: str
    metric: str
    current_value: float
    baseline_value: float
    absolute_change: float
    relative_change_pct: float | None
    severity: Literal["low", "medium", "high", "positive"]
    confidence: Literal["low", "medium", "high"]
    sample_size: int
    reason: str
    supporting_dimensions: dict[str, Any] = Field(default_factory=dict)
    data_quality_warnings: list[str] = Field(default_factory=list)


CrossDomainCategory = Literal[
    "billing_integrity",
    "safety_pattern",
    "vendor_operational_divergence",
    "shift_readiness_pattern",
    "data_integrity_anomaly",
]


class CrossDomainSignal(BaseModel):
    """One correlated deterministic signal contributing to a cross-domain anomaly."""

    metric: str
    current_value: float | int | None
    baseline_value: float | int | None = None
    peer_median: float | int | None = None
    relative_change_pct: float | None = None
    # "worse" / "better" describe operational direction, not raw arithmetic sign.
    direction: Literal["worse", "better", "stable"]
    weight: float
    note: str | None = None


class RiskComponent(BaseModel):
    """Explainable additive contribution to cross_signal_risk_score."""

    name: str
    value: float
    detail: str


class CrossDomainAnomaly(BaseModel):
    id: str
    category: CrossDomainCategory
    entity_type: str
    entity_name: str
    title: str
    severity: Literal["low", "medium", "high"]
    confidence: Literal["low", "medium", "high"]
    # Never a fraud probability; an explainable prioritization score in [0, 100].
    cross_signal_risk_score: float
    signals: list[CrossDomainSignal] = Field(default_factory=list)
    why_flagged: str
    recommended_investigation: list[str] = Field(default_factory=list)
    risk_components: list[RiskComponent] = Field(default_factory=list)
    sample_size: int
    month: str
    baseline_month: str | None = None
    supporting_dimensions: dict[str, Any] = Field(default_factory=dict)
    data_quality_warnings: list[str] = Field(default_factory=list)

