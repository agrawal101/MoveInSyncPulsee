from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentFinding(StrictAgentModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=280)
    evidence_id: str | None = Field(
        default=None,
        description="Exact evidence_id adjacent to the cited aggregate; required for numeric fields.",
    )
    entity: str | None = Field(
        default=None,
        description="Exact entity label from the cited evidence when applicable.",
    )
    metric: str | None = Field(
        default=None,
        description="Exact metric key associated with evidence_id; required for numeric fields.",
    )
    current_value: float | int | None = None
    baseline_value: float | int | None = None
    change: float | int | None = None
    relative_change_pct: float | int | None = None
    sample_size: int | None = None


class GroundedAgentFinding(AgentFinding):
    """LLM-facing finding: every item must bind to one deterministic record."""

    evidence_id: str = Field(
        min_length=4,
        max_length=120,
        description="Copy the exact evidence_id from the cited aggregate object.",
    )
    metric: str = Field(
        min_length=1,
        max_length=100,
        description="Copy the exact metric associated with evidence_id.",
    )
    current_value: float | int = Field(
        description="Copy the exact current value associated with evidence_id."
    )


class RecommendedAction(StrictAgentModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=240)
    requires_approval: bool = True


class EvidenceReference(StrictAgentModel):
    tool: str
    description: str = Field(max_length=160)


class ExecutionMetadata(StrictAgentModel):
    request_id: str
    tools_called: list[str] = Field(default_factory=list)
    tool_durations_ms: dict[str, float] = Field(default_factory=dict)
    llm_duration_ms: float | None = None
    duration_ms: float
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    fallback_used: bool = False
    error_category: str | None = None
    repair_attempted: bool = False
    validator_rejection: dict[str, str | None] | None = None
    validation_result: Literal["passed", "repaired", "deterministic_fallback"]


class AgentSynthesis(StrictAgentModel):
    """Provider-facing schema; runtime metadata is deliberately excluded."""

    answer: str = Field(max_length=1000)
    summary: str = Field(max_length=500)
    severity: Literal["low", "medium", "high", "positive", "informational"]
    confidence: Literal["low", "medium", "high"]
    synthesis_mode: Literal["llm"]
    findings: list[GroundedAgentFinding] = Field(min_length=1, max_length=6)
    recommended_actions: list[RecommendedAction] = Field(min_length=1, max_length=4)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=7)
    data_quality_warnings: list[str] = Field(max_length=12)


class AgentResponse(StrictAgentModel):
    answer: str
    summary: str
    severity: Literal["low", "medium", "high", "positive", "informational"]
    confidence: Literal["low", "medium", "high"]
    synthesis_mode: Literal["llm", "deterministic_fallback"] = "llm"
    findings: list[AgentFinding] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    data_quality_warnings: list[str] = Field(default_factory=list)
    execution: ExecutionMetadata | None = None


class AgentQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    month: str
    baseline_month: str | None = None


class InvestigationRequest(BaseModel):
    anomaly_id: str
    month: str = "2026-07"


class ExecutiveSummaryRequest(BaseModel):
    month: str
    baseline_month: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    llm_configured: bool


class DelayAnalysisResponse(BaseModel):
    month: str
    filters: dict[str, str | None]
    reasons: list[dict[str, Any]]
    trip_evidence: list[dict[str, Any]]


class DataQualityResponse(BaseModel):
    preprocessing: dict[str, Any]
    missing_ride_joins: dict[str, int]
    ambiguous_trip_dimensions: int
    high_null_fields: list[dict[str, Any]]
    warnings: list[str]
