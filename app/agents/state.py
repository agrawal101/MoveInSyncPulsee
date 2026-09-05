from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    request_id: str
    endpoint: str
    mode: str
    question: str
    month: str
    baseline_month: str | None
    anomaly_id: str | None
    tool_plan: list[dict[str, Any]]
    evidence: dict[str, Any]
    warnings: list[str]
    tools_called: list[str]
    tool_durations_ms: dict[str, float]
    llm_duration_ms: float
    llm_provider: str | None
    llm_model: str | None
    input_tokens: int | None
    output_tokens: int | None
    fallback_used: bool
    provider_error_category: str | None
    repair_attempted: bool
    validator_rejection: dict[str, str | None] | None
    validation_result: str
    started_at: float
    response: Any
