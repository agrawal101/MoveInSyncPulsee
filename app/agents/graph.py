from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import replace
from typing import Any

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agents.evidence import attach_evidence_ids, compact_evidence
from app.agents.fallback import build_fallback
from app.agents.prompts import SYSTEM_PROMPT
from app.agents.state import AgentState
from app.agents.tools import TOOL_REGISTRY
from app.agents.validation import (
    UnsupportedEvidenceError,
    sanitize_numeric_prose,
    validate_response_evidence,
)
from app.llm.provider import LLMProvider, LLMProviderError, LLMResult
from app.models.agent import AgentResponse, AgentSynthesis

logger = logging.getLogger(__name__)


def _vendor(question: str) -> str | None:
    match = re.search(
        r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+\s+Travel)",
        question,
    )
    return match.group(1) if match else None


def _previous_label(month: str) -> str:
    year, number = map(int, month.split("-"))
    number -= 1
    if number == 0:
        year -= 1
        number = 12
    return f"{year:04d}-{number:02d}"


def build_plan(state: AgentState) -> AgentState:
    month = state["month"]
    baseline = state.get("baseline_month") or _previous_label(month)
    mode = state.get("mode", "query")
    if mode == "report":
        names = [
            ("get_monthly_overview_tool", {"month": month}),
            ("detect_anomalies_tool", {"month": month}),
            (
                "compare_vendor_performance_tool",
                {"current_month": month, "baseline_month": baseline},
            ),
            ("get_shift_readiness_tool", {"month": month}),
            ("analyze_safety_alerts_tool", {"month": month}),
            ("analyze_cost_tool", {"month": month}),
            ("get_data_quality_report_tool", {}),
        ]
    elif mode == "investigate":
        names = [("detect_anomalies_tool", {"month": month})]
    else:
        question = state["question"].lower()
        vendor = _vendor(state["question"])
        if vendor:
            names = [
                (
                    "analyze_vendor_tool",
                    {
                        "vendor": vendor,
                        "month": month,
                        "baseline_month": baseline,
                    },
                ),
                ("analyze_safety_alerts_tool", {"month": month, "vendor": vendor}),
                ("analyze_delay_causes_tool", {"month": month, "vendor": vendor}),
                ("detect_anomalies_tool", {"month": month}),
            ]
        elif "vendor" in question:
            names = [
                (
                    "compare_vendor_performance_tool",
                    {"current_month": month, "baseline_month": baseline},
                ),
                ("detect_anomalies_tool", {"month": month}),
            ]
        elif "shift" in question or "pickup" in question:
            names = [("get_shift_readiness_tool", {"month": month})]
        elif "delay" in question or "caused" in question:
            names = [("analyze_delay_causes_tool", {"month": month})]
        elif "cost" in question or "billing" in question:
            names = [
                ("analyze_cost_tool", {"month": month}),
                ("get_data_quality_report_tool", {}),
            ]
        elif "safety" in question or "alert" in question or "office" in question:
            names = [("analyze_safety_alerts_tool", {"month": month})]
        elif "experience" in question or "rating" in question:
            names = [("get_experience_metrics_tool", {"month": month})]
        else:
            names = [
                ("get_monthly_overview_tool", {"month": month}),
                ("detect_anomalies_tool", {"month": month}),
            ]
    return {"tool_plan": [{"name": name, "arguments": args} for name, args in names]}


def _sum_tokens(first: int | None, second: int | None) -> int | None:
    if first is None and second is None:
        return None
    return (first or 0) + (second or 0)


def _combine_results(first: LLMResult, second: LLMResult) -> LLMResult:
    return replace(
        second,
        latency_ms=round(first.latency_ms + second.latency_ms, 2),
        input_tokens=_sum_tokens(first.input_tokens, second.input_tokens),
        output_tokens=_sum_tokens(first.output_tokens, second.output_tokens),
        fallback_used=first.fallback_used or second.fallback_used,
        error_category=second.error_category or first.error_category,
        validation_result=(
            "repaired"
            if "repaired" in {first.validation_result, second.validation_result}
            else "passed"
        ),
    )


class MobilityAgentGraph:
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        graph = StateGraph(AgentState)
        graph.add_node("plan", build_plan)
        graph.add_node("collect_evidence", self._collect)
        graph.add_node("check_quality", self._quality)
        graph.add_node("synthesize", self._synthesize)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "collect_evidence")
        graph.add_edge("collect_evidence", "check_quality")
        graph.add_edge("check_quality", "synthesize")
        graph.add_edge("synthesize", END)
        self.graph = graph.compile()

    def _invoke_tool(
        self,
        state: AgentState,
        name: str,
        args: dict[str, Any],
    ) -> tuple[Any, float]:
        started = time.perf_counter()
        logger.info(
            "agent_tool_start",
            extra={"request_id": state["request_id"], "tool": name},
        )
        value = TOOL_REGISTRY[name].invoke(args)
        duration = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "agent_tool_complete",
            extra={
                "request_id": state["request_id"],
                "tool": name,
                "duration_ms": duration,
            },
        )
        return value, duration

    def _collect(self, state: AgentState) -> AgentState:
        evidence: dict[str, Any] = {}
        called: list[str] = []
        durations: dict[str, float] = {}
        for spec in state["tool_plan"]:
            name = spec["name"]
            evidence[name], durations[name] = self._invoke_tool(
                state, name, spec["arguments"]
            )
            called.append(name)

        if state.get("mode") == "investigate":
            anomaly = next(
                (
                    item
                    for item in evidence["detect_anomalies_tool"]
                    if item["id"] == state.get("anomaly_id")
                ),
                None,
            )
            if anomaly is None:
                raise LookupError(f"Anomaly not found: {state.get('anomaly_id')}")
            evidence["selected_anomaly"] = anomaly
            if anomaly["entity_type"] == "vendor":
                vendor = anomaly["entity_name"]
                extra = [
                    (
                        "analyze_vendor_tool",
                        {
                            "vendor": vendor,
                            "month": state["month"],
                            "baseline_month": state.get("baseline_month")
                            or _previous_label(state["month"]),
                        },
                    ),
                    (
                        "analyze_safety_alerts_tool",
                        {"month": state["month"], "vendor": vendor},
                    ),
                    (
                        "analyze_delay_causes_tool",
                        {"month": state["month"], "vendor": vendor},
                    ),
                ]
            elif anomaly["entity_type"] == "shift":
                extra = [("get_shift_readiness_tool", {"month": state["month"]})]
            else:
                extra = [("get_monthly_overview_tool", {"month": state["month"]})]
            for name, args in extra:
                evidence[name], durations[name] = self._invoke_tool(state, name, args)
                called.append(name)
        return {
            "evidence": evidence,
            "tools_called": called,
            "tool_durations_ms": durations,
        }

    def _quality(self, state: AgentState) -> AgentState:
        warnings: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"data_quality_warnings", "warnings"} and isinstance(
                        item, list
                    ):
                        warnings.extend(
                            str(entry.get("message", entry))
                            if isinstance(entry, dict)
                            else str(entry)
                            for entry in item
                        )
                    else:
                        walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(state["evidence"])
        return {"warnings": list(dict.fromkeys(warnings))}

    @staticmethod
    def _validated_response(
        generated: LLMResult,
        evidence: dict[str, Any],
        *,
        conservative_repair: bool = False,
    ) -> AgentResponse:
        synthesis = AgentSynthesis.model_validate(
            generated.output.model_dump(exclude={"execution"})
        )
        synthesis = sanitize_numeric_prose(synthesis)
        if conservative_repair:
            # A repair gets one chance. Omit optional comparison claims so a second
            # unsupported value cannot leak or trigger an unbounded repair loop.
            for finding in synthesis.findings:
                finding.baseline_value = None
                finding.change = None
                finding.relative_change_pct = None
                finding.sample_size = None
        validate_response_evidence(synthesis, evidence)
        response = AgentResponse.model_validate(synthesis.model_dump())
        response.synthesis_mode = "llm"
        response.execution = None
        # The service appends the exact deterministic warnings after synthesis.
        response.data_quality_warnings = []
        return response

    def _synthesize(self, state: AgentState) -> AgentState:
        evidence = compact_evidence(state["evidence"])
        if state.get("mode") == "investigate" and "selected_anomaly" in evidence:
            # Investigation receives only the chosen anomaly, not unrelated anomaly rows.
            evidence["detect_anomalies_tool"] = [evidence["selected_anomaly"]]
        provider_evidence = attach_evidence_ids(evidence)

        task = state.get("question") or (
            "Investigate anomaly " + str(state.get("anomaly_id"))
        )
        started = time.perf_counter()
        validation_result = "passed"
        repair_attempted = False
        validator_rejection: dict[str, str | None] | None = None
        try:
            generated = self.provider.generate_structured(
                system_prompt=SYSTEM_PROMPT,
                task=task,
                evidence=provider_evidence,
                response_model=AgentSynthesis,
                workflow=state.get("mode", "query"),
            )
            try:
                response = self._validated_response(generated, provider_evidence)
            except UnsupportedEvidenceError as validation_error:
                repair_attempted = True
                validator_rejection = validation_error.log_context()
                safe_context = (
                    validator_rejection
                    if os.getenv("LLM_VALIDATION_DEBUG", "false").lower()
                    in {"1", "true", "yes", "on"}
                    else {}
                )
                logger.warning(
                    "agent_evidence_validation_repair",
                    extra={
                        "request_id": state["request_id"],
                        "endpoint": state["endpoint"],
                        "provider": generated.provider,
                        "model": generated.model,
                        "error_category": type(validation_error).__name__,
                        **safe_context,
                    },
                )
                repair_task = (
                    task
                    + "\n\nRepair the response once for this exact safe validator issue: "
                    + str(validation_error)
                    + ". For every numeric finding, copy one exact evidence_id and its "
                    "exact metric and current_value. Set baseline_value, change, "
                    "relative_change_pct, and sample_size to null. Do not put numbers in prose. Do not "
                    "introduce calculated values, thresholds, dates, ranks, or totals."
                )
                repaired = self.provider.generate_structured(
                    system_prompt=SYSTEM_PROMPT,
                    task=repair_task,
                    evidence=provider_evidence,
                    response_model=AgentSynthesis,
                    workflow=state.get("mode", "query"),
                )
                try:
                    response = self._validated_response(
                        repaired,
                        provider_evidence,
                        conservative_repair=True,
                    )
                except UnsupportedEvidenceError as second_error:
                    validator_rejection = second_error.log_context()
                    second_context = (
                        second_error.log_context()
                        if os.getenv("LLM_VALIDATION_DEBUG", "false").lower()
                        in {"1", "true", "yes", "on"}
                        else {}
                    )
                    logger.warning(
                        "agent_evidence_validation_failed",
                        extra={
                            "request_id": state["request_id"],
                            "endpoint": state["endpoint"],
                            "provider": repaired.provider,
                            "model": repaired.model,
                            "error_category": type(second_error).__name__,
                            **second_context,
                        },
                    )
                    raise
                generated = _combine_results(generated, repaired)
                validation_result = "repaired"

            if generated.validation_result == "repaired":
                validation_result = "repaired"
                repair_attempted = True

            return {
                "response": response,
                "llm_duration_ms": generated.latency_ms,
                "llm_provider": generated.provider,
                "llm_model": generated.model,
                "input_tokens": generated.input_tokens,
                "output_tokens": generated.output_tokens,
                "fallback_used": generated.fallback_used,
                "provider_error_category": generated.error_category,
                "repair_attempted": repair_attempted,
                "validator_rejection": validator_rejection,
                "validation_result": validation_result,
            }
        except (LLMProviderError, UnsupportedEvidenceError, ValidationError) as exc:
            duration = round((time.perf_counter() - started) * 1000, 2)
            category = type(exc).__name__
            logger.warning(
                "llm_deterministic_fallback",
                extra={
                    "request_id": state["request_id"],
                    "endpoint": state["endpoint"],
                    "duration_ms": duration,
                    "fallback_used": True,
                    "validation_result": "deterministic_fallback",
                    "error_category": category,
                },
            )
            response = build_fallback(
                state.get("mode", "query"),
                evidence,
                state.get("warnings", []),
                str(exc),
                state.get("question", ""),
            )
            return {
                "response": response,
                "llm_duration_ms": duration,
                "llm_provider": None,
                "llm_model": None,
                "input_tokens": None,
                "output_tokens": None,
                "fallback_used": True,
                "provider_error_category": category,
                "repair_attempted": repair_attempted,
                "validator_rejection": validator_rejection,
                "validation_result": "deterministic_fallback",
            }
