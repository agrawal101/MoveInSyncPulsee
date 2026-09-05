from __future__ import annotations

from typing import Any

from app.models.agent import (
    AgentFinding,
    AgentResponse,
    EvidenceReference,
    RecommendedAction,
)

FALLBACK_NOTICE = "AI synthesis unavailable — showing analytics-backed summary."


def _refs(evidence: dict[str, Any]) -> list[EvidenceReference]:
    return [
        EvidenceReference(tool=key, description="Deterministic analytics evidence")
        for key in evidence
        if key != "selected_anomaly"
    ]


def _warnings(warnings: list[str]) -> list[str]:
    return list(dict.fromkeys(warnings + [FALLBACK_NOTICE]))


def build_fallback(
    mode: str,
    evidence: dict[str, Any],
    warnings: list[str],
    _error: str,
    question: str = "",
) -> AgentResponse:
    if mode == "investigate":
        return _investigation(evidence, warnings)
    if mode == "report":
        return _report(evidence, warnings)
    return _query(evidence, warnings, question)


def _investigation(evidence: dict[str, Any], warnings: list[str]) -> AgentResponse:
    anomaly = evidence.get("selected_anomaly", {})
    metric = anomaly.get("metric", "detected_deviation")
    findings = [
        AgentFinding(
            title="Detected operational deviation",
            description=anomaly.get(
                "reason", "Deterministic anomaly requires targeted review."
            ),
            metric=metric,
            current_value=anomaly.get("current_value"),
            baseline_value=anomaly.get("baseline_value"),
            change=anomaly.get("absolute_change"),
            sample_size=anomaly.get("sample_size"),
        )
    ]
    safety = evidence.get("analyze_safety_alerts_tool")
    if safety:
        categories = safety.get("alert_type_distribution", [])[:3]
        findings.append(
            AgentFinding(
                title="Safety-event context",
                description="Largest observed categories: "
                + ", ".join(str(item.get("category")) for item in categories)
                + ".",
                metric="alert_count",
                current_value=safety.get("alert_count"),
                sample_size=safety.get("trip_count"),
            )
        )
    return AgentResponse(
        answer=(
            "Deterministic evidence confirms a material deviation. Review the "
            "concentrated contributing dimensions before taking vendor-wide action."
        ),
        summary=(
            f"{anomaly.get('entity_name', 'Entity')} requires targeted investigation "
            f"of {metric.replace('_', ' ')}."
        ),
        severity=anomaly.get("severity", "medium"),
        confidence=anomaly.get("confidence", "medium"),
        synthesis_mode="deterministic_fallback",
        findings=findings,
        recommended_actions=[
            RecommendedAction(
                title="Review concentrated evidence",
                description=(
                    "Inspect the leading alert categories, offices, and repeated vehicles; "
                    "validate severity quality before intervention."
                ),
            ),
            RecommendedAction(
                title="Request a focused corrective plan",
                description=(
                    "Use the observed evidence to define targeted operational follow-up."
                ),
            ),
        ],
        evidence=_refs(evidence),
        data_quality_warnings=_warnings(warnings),
    )


def _report(evidence: dict[str, Any], warnings: list[str]) -> AgentResponse:
    overview = evidence.get("get_monthly_overview_tool", {}).get("metrics", {})
    anomalies = evidence.get("detect_anomalies_tool", [])
    shifts = evidence.get("get_shift_readiness_tool", {}).get("shifts", [])
    cost = evidence.get("analyze_cost_tool", {})
    findings: list[AgentFinding] = []
    for key, title in [
        ("total_trips", "Mobility volume"),
        ("delay_rate", "Reliability movement"),
        ("no_show_rate", "No-show movement"),
    ]:
        item = overview.get(key, {})
        findings.append(
            AgentFinding(
                title=title,
                description="Current and prior values come from monthly evidence.",
                metric=key,
                current_value=item.get("current_value"),
                baseline_value=item.get("previous_value"),
                change=item.get("absolute_change"),
                sample_size=item.get("sample_size"),
            )
        )
    if anomalies:
        anomaly = anomalies[0]
        findings.append(
            AgentFinding(
                title="Highest-priority anomaly",
                description=anomaly.get("reason", ""),
                metric=anomaly.get("metric"),
                current_value=anomaly.get("current_value"),
                baseline_value=anomaly.get("baseline_value"),
                change=anomaly.get("absolute_change"),
                sample_size=anomaly.get("sample_size"),
            )
        )
    if shifts:
        shift = shifts[0]
        findings.append(
            AgentFinding(
                title="Shift-readiness priority",
                description=(
                    f"Shift {shift.get('shift_type')} has the highest supported risk "
                    "among eligible samples."
                ),
                metric="risk_score",
                current_value=shift.get("risk_score"),
                sample_size=shift.get("pickup_sample"),
            )
        )
    findings.append(
        AgentFinding(
            title="Cost coverage",
            description="Distance-normalized cost excludes invalid cost/distance rows.",
            metric="distance_metric_coverage_pct",
            current_value=cost.get("distance_metric_coverage_pct"),
            sample_size=cost.get("valid_distance_rows"),
        )
    )
    return AgentResponse(
        answer=(
            "Operational reliability and safety priorities are summarized from current "
            "deterministic evidence. Leadership should focus on the highest normalized "
            "safety deviation, the leading shift risk, and cost-data coverage."
        ),
        summary="Executive mobility brief generated from analytics-backed evidence.",
        severity=(
            "high" if any(item.get("severity") == "high" for item in anomalies) else "medium"
        ),
        confidence="high",
        synthesis_mode="deterministic_fallback",
        findings=findings,
        recommended_actions=[
            RecommendedAction(
                title="Address the highest safety deviation",
                description="Run a targeted review using alert type, office, and vehicle evidence.",
            ),
            RecommendedAction(
                title="Stabilize the highest-risk shift",
                description=(
                    "Review pickup lateness and no-show contributors for the top supported shift."
                ),
            ),
            RecommendedAction(
                title="Improve billing-distance coverage",
                description=(
                    "Resolve excluded distance records before relying broadly on cost per kilometre."
                ),
            ),
        ],
        evidence=_refs(evidence),
        data_quality_warnings=_warnings(warnings),
    )


def _query(
    evidence: dict[str, Any], warnings: list[str], question: str
) -> AgentResponse:
    findings: list[AgentFinding] = []
    vendor_detail = evidence.get("analyze_vendor_tool")
    safety = evidence.get("analyze_safety_alerts_tool")
    delay = evidence.get("analyze_delay_causes_tool")
    cost = evidence.get("analyze_cost_tool")
    shifts = evidence.get("get_shift_readiness_tool", {}).get("shifts", [])
    anomalies = evidence.get("detect_anomalies_tool", [])
    vendors = evidence.get("compare_vendor_performance_tool", {}).get("vendors", [])
    improving = (
        next(
            (item for item in anomalies if item.get("severity") == "positive"),
            None,
        )
        if "improv" in question.lower()
        else None
    )
    summary: str | None = None
    answer = "The most relevant deterministic result is provided below."
    actions = [
        RecommendedAction(
            title="Review evidence",
            description="Use the cited deterministic result for operational follow-up.",
        )
    ]
    severity = "informational"
    if vendor_detail:
        vendor = vendor_detail.get("vendor", "Selected vendor")
        metrics = vendor_detail.get("metrics", {})
        alert_rate = metrics.get("alerts_per_1000_trips", {})
        findings.append(
            AgentFinding(
                title="Safety rate requires attention",
                description=(
                    "The normalized alert rate deteriorated while other service metrics "
                    "must be reviewed separately."
                ),
                metric="alerts_per_1000_trips",
                current_value=alert_rate.get("current_value"),
                baseline_value=alert_rate.get("baseline_value"),
                change=alert_rate.get("absolute_change"),
                sample_size=alert_rate.get("sample_size"),
            )
        )
        for metric, title in [
            ("average_delay_minutes", "Average delay improved"),
            ("no_show_rate", "No-show performance improved"),
        ]:
            item = metrics.get(metric, {})
            if item.get("absolute_change") is not None and item["absolute_change"] < 0:
                findings.append(
                    AgentFinding(
                        title=title,
                        description=(
                            "This service metric improved versus the selected baseline."
                        ),
                        metric=metric,
                        current_value=item.get("current_value"),
                        baseline_value=item.get("baseline_value"),
                        change=item.get("absolute_change"),
                        sample_size=item.get("sample_size"),
                    )
                )
        categories = (safety or {}).get("alert_type_distribution", [])[:3]
        if categories:
            findings[0].description += " Leading categories: " + ", ".join(
                str(item.get("category")) for item in categories
            ) + "."
        summary = f"{vendor} needs a targeted safety investigation"
        answer = (
            "The risk is concentrated in normalized safety alerts, not uniform "
            "deterioration across every service metric."
        )
        actions = [
            RecommendedAction(
                title="Investigate leading alert categories",
                description=(
                    "Review the concentrated categories, office, and repeated-vehicle evidence."
                ),
            ),
            RecommendedAction(
                title="Keep service trends separate",
                description=(
                    "Do not treat improving delay or no-show performance as proof that the "
                    "safety concern is resolved."
                ),
            ),
        ]
        severity = "high"
    elif delay and delay.get("reasons"):
        top = delay["reasons"][0]
        findings.append(
            AgentFinding(
                title=f"Leading observed delay reason: {top.get('delay_reason')}",
                description="This category has the largest trip count in delay evidence.",
                metric="trip_count",
                current_value=top.get("trip_count"),
                sample_size=int(top["trip_count"]) if top.get("trip_count") is not None else None,
            )
        )
        summary = "Leading delay cause identified from aggregate evidence"
        answer = "Prioritize the leading observed delay category for operational review."
        actions = [
            RecommendedAction(
                title="Review the leading delay category",
                description="Inspect the relevant operating window and route conditions.",
            )
        ]
    elif vendors:
        top = vendors[0]
        findings.append(
            AgentFinding(
                title=f"Investigate {top.get('vendor')}",
                description=(
                    "This vendor is first in the deterministic comparison for the selected month."
                ),
                metric="deterioration_score",
                current_value=top.get("deterioration_score"),
            )
        )
    elif improving:
        findings.append(
            AgentFinding(
                title="Strongest positive movement",
                description=improving.get("reason", ""),
                metric=improving.get("metric"),
                current_value=improving.get("current_value"),
                baseline_value=improving.get("baseline_value"),
                change=improving.get("absolute_change"),
                sample_size=improving.get("sample_size"),
            )
        )
    elif cost:
        findings.append(
            AgentFinding(
                title="Cost metric coverage",
                description="Cost/km uses valid cost and positive-distance rows only.",
                metric="distance_metric_coverage_pct",
                current_value=cost.get("distance_metric_coverage_pct"),
                sample_size=cost.get("valid_distance_rows"),
            )
        )
    elif shifts:
        top = shifts[0]
        findings.append(
            AgentFinding(
                title="Highest supported shift risk",
                description=(
                    f"Shift {top.get('shift_type')} ranks first among eligible samples."
                ),
                metric="risk_score",
                current_value=top.get("risk_score"),
                sample_size=top.get("pickup_sample"),
            )
        )
    elif anomalies:
        top = anomalies[0]
        findings.append(
            AgentFinding(
                title="Highest-priority deviation",
                description=top.get("reason", ""),
                metric=top.get("metric"),
                current_value=top.get("current_value"),
                baseline_value=top.get("baseline_value"),
                change=top.get("absolute_change"),
                sample_size=top.get("sample_size"),
            )
        )
    else:
        findings.append(
            AgentFinding(
                title="Deterministic evidence retrieved",
                description="Review the supporting evidence returned with this response.",
            )
        )
    return AgentResponse(
        answer=answer,
        summary=summary or findings[0].title,
        severity=severity,
        confidence="high",
        synthesis_mode="deterministic_fallback",
        findings=findings,
        recommended_actions=actions,
        evidence=_refs(evidence),
        data_quality_warnings=_warnings(warnings),
    )
