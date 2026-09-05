from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any


SAFE_AGGREGATE_TOOLS = {
    "get_monthly_overview_tool",
    "analyze_vendor_tool",
    "analyze_cost_tool",
    "get_experience_metrics_tool",
    "selected_anomaly",
}

ENTITY_KEYS = (
    "entity_name",
    "vendor",
    "office",
    "shift_type",
    "category",
    "delay_reason",
    "vehicle",
    "month",
    "current_month",
)
TOOL_LABELS = {
    "get_monthly_overview_tool": "overview",
    "analyze_vendor_tool": "vendor",
    "compare_vendor_performance_tool": "vendor_compare",
    "analyze_safety_alerts_tool": "safety",
    "analyze_delay_causes_tool": "delay",
    "get_shift_readiness_tool": "shift",
    "analyze_cost_tool": "cost",
    "get_experience_metrics_tool": "experience",
    "detect_anomalies_tool": "anomaly",
    "detect_cross_domain_anomalies_tool": "cross_anomaly",
    "selected_anomaly": "selected_anomaly",
    "get_data_quality_report_tool": "quality",
}
COLLECTION_LABELS = {
    "vendors",
    "shifts",
    "reasons",
    "severity_distribution",
    "alert_type_distribution",
    "vendor_concentration",
    "office_concentration",
    "repeated_vehicle_patterns",
    "high_null_fields",
}


def _numeric(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _evidence_id(
    tool: str,
    path: tuple[str, ...],
    entities: tuple[str, ...],
    metric: str,
) -> str:
    collection = next((part for part in path if part in COLLECTION_LABELS), "")
    dates = tuple(value for value in entities if re.fullmatch(r"\d{4}-\d{2}", value))
    labels = tuple(value for value in entities if value not in dates)
    pieces = (
        TOOL_LABELS.get(tool, tool.removesuffix("_tool")),
        collection,
        *labels,
        metric,
        *dates,
    )
    return "ev_" + "_".join(filter(None, (_slug(part) for part in pieces)))[:120]


def attach_evidence_ids(evidence: dict[str, Any]) -> dict[str, Any]:
    """Add stable IDs beside aggregate values without changing their values."""

    enriched = deepcopy(evidence)

    def walk(
        item: Any,
        tool: str,
        path: tuple[str, ...],
        inherited_entities: tuple[str, ...],
    ) -> None:
        if isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, tool, (*path, str(index)), inherited_entities)
            return
        if not isinstance(item, dict):
            return

        local_entities = tuple(
            str(item[key])
            for key in ENTITY_KEYS
            if isinstance(item.get(key), str) and item[key]
        )
        entities = tuple(dict.fromkeys((*inherited_entities, *local_entities)))
        original_items = list(item.items())
        declared_metric = item.get("metric")
        numeric_fields = {
            str(key): value for key, value in original_items if _numeric(value)
        }
        if isinstance(declared_metric, str) and numeric_fields:
            item["evidence_id"] = _evidence_id(
                tool, path, entities, declared_metric
            )
        elif numeric_fields:
            item["evidence_ids"] = {
                field: _evidence_id(tool, path, entities, field)
                for field in numeric_fields
            }

        for key, child in original_items:
            walk(child, tool, (*path, str(key)), entities)

    for tool, value in enriched.items():
        walk(value, tool, (), ())
    return enriched


def compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Bound model context to aggregate, decision-grade deterministic evidence."""

    compact: dict[str, Any] = {}
    for tool, value in evidence.items():
        if tool == "detect_anomalies_tool" and isinstance(value, list):
            compact[tool] = [
                item for item in value if item.get("severity") in {"high", "medium"}
            ][:6] + [
                item for item in value if item.get("severity") == "positive"
            ][:3]
        elif tool == "detect_cross_domain_anomalies_tool" and isinstance(value, list):
            compact[tool] = [
                item for item in value if item.get("severity") in {"high", "medium"}
            ][:6]
        elif tool == "compare_vendor_performance_tool" and isinstance(value, dict):
            compact[tool] = {**value, "vendors": value.get("vendors", [])[:6]}
        elif tool == "get_shift_readiness_tool" and isinstance(value, dict):
            eligible = [
                item
                for item in value.get("shifts", [])
                if item.get("pickup_sample", 0) >= 500
            ]
            compact[tool] = {**value, "shifts": eligible[:6]}
        elif tool == "analyze_safety_alerts_tool" and isinstance(value, dict):
            compact[tool] = {
                **value,
                "alert_type_distribution": value.get("alert_type_distribution", [])[:7],
                "vendor_concentration": value.get("vendor_concentration", [])[:5],
                "office_concentration": value.get("office_concentration", [])[:5],
                "repeated_vehicle_patterns": value.get("repeated_vehicle_patterns", [])[:5],
            }
        elif tool == "analyze_delay_causes_tool" and isinstance(value, dict):
            # Trip-level examples are intentionally excluded from all model prompts.
            compact[tool] = {
                key: item
                for key, item in value.items()
                if key != "trip_evidence"
            }
        elif tool == "get_data_quality_report_tool" and isinstance(value, dict):
            compact[tool] = {
                "missing_ride_joins": value.get("missing_ride_joins", {}),
                "ambiguous_trip_dimensions": value.get("ambiguous_trip_dimensions"),
                "high_null_fields": value.get("high_null_fields", [])[:12],
                "warnings": value.get("warnings", []),
            }
        elif tool in SAFE_AGGREGATE_TOOLS:
            compact[tool] = value
    return compact
