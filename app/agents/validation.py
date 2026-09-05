from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from app.models.agent import AgentResponse, AgentSynthesis


@dataclass(frozen=True)
class EvidenceRuleFailure:
    field_path: str
    rejected_value: Any
    validation_rule: str
    nearest_supported_value: Any = None


class UnsupportedEvidenceError(ValueError):
    """Safe, structured rejection details suitable for development logs."""

    def __init__(self, failure: EvidenceRuleFailure):
        self.failure = failure
        nearest = (
            f"; nearest_supported={failure.nearest_supported_value!r}"
            if failure.nearest_supported_value is not None
            else ""
        )
        super().__init__(
            f"field={failure.field_path}; rule={failure.validation_rule}; "
            f"rejected={failure.rejected_value!r}{nearest}"
        )

    def log_context(self) -> dict[str, Any]:
        return {
            "field_path": self.failure.field_path,
            "rejected_value": str(self.failure.rejected_value)[:160],
            "validation_rule": self.failure.validation_rule,
            "nearest_supported_value": (
                str(self.failure.nearest_supported_value)[:160]
                if self.failure.nearest_supported_value is not None
                else None
            ),
        }


@dataclass(frozen=True)
class EvidenceRecord:
    metric: str
    entities: frozenset[str]
    values: dict[str, float]


ROLE_KEYS = {
    "current_value": ("current_value", "value"),
    "baseline_value": ("baseline_value", "previous_value"),
    "change": ("change", "absolute_change"),
    "relative_change_pct": ("relative_change_pct",),
}
SAMPLE_KEYS = (
    "sample_size",
    "pickup_sample",
    "trip_count",
    "feedback_rows",
    "billed_rows",
    "valid_distance_rows",
    "rider_legs",
)
ENTITY_KEYS = (
    "entity_name",
    "vendor",
    "office",
    "shift_type",
    "category",
    "delay_reason",
    "vehicle",
)
NUMERIC_TEXT = re.compile(r"(?<![A-Za-z_])[-+]?\d[\d,]*(?:\.\d+)?%?")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _number(value: Any) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ):
        return float(value)
    return None


def _first_number(item: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        number = _number(item.get(key))
        if number is not None:
            return number
    return None


def _record_values(item: dict[str, Any], metric: str) -> dict[str, float]:
    values: dict[str, float] = {}
    if isinstance(item.get("metric"), str):
        for role, keys in ROLE_KEYS.items():
            number = _first_number(item, keys)
            if number is not None:
                values[role] = number
    else:
        current = _number(item.get(metric))
        if current is not None:
            values["current_value"] = current
    sample = _first_number(item, SAMPLE_KEYS)
    if sample is not None:
        values["sample_size"] = sample
    return values


def _evidence_index(evidence: dict[str, Any]) -> dict[str, EvidenceRecord]:
    indexed: dict[str, EvidenceRecord] = {}

    def walk(item: Any, inherited_entities: tuple[str, ...] = ()) -> None:
        if isinstance(item, list):
            for child in item:
                walk(child, inherited_entities)
            return
        if not isinstance(item, dict):
            return
        local = tuple(
            str(item[key])
            for key in ENTITY_KEYS
            if isinstance(item.get(key), str) and item[key]
        )
        entities = tuple(dict.fromkeys((*inherited_entities, *local)))
        evidence_id = item.get("evidence_id")
        metric = item.get("metric")
        if isinstance(evidence_id, str) and isinstance(metric, str):
            indexed[evidence_id] = EvidenceRecord(
                metric=metric,
                entities=frozenset(entities),
                values=_record_values(item, metric),
            )
        evidence_ids = item.get("evidence_ids")
        if isinstance(evidence_ids, dict):
            for field, item_id in evidence_ids.items():
                if isinstance(item_id, str):
                    indexed[item_id] = EvidenceRecord(
                        metric=str(field),
                        entities=frozenset(entities),
                        values=_record_values(item, str(field)),
                    )
        for key, child in item.items():
            if key not in {"evidence_id", "evidence_ids"}:
                walk(child, entities)

    walk(evidence)
    return indexed


def _fail(
    field_path: str,
    rejected_value: Any,
    rule: str,
    nearest: Any = None,
) -> UnsupportedEvidenceError:
    return UnsupportedEvidenceError(
        EvidenceRuleFailure(field_path, rejected_value, rule, nearest)
    )


def _strip_numeric_sentences(text: str, replacement: str) -> str:
    kept = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT.split(text.strip())
        if sentence.strip() and not NUMERIC_TEXT.search(sentence)
    ]
    return " ".join(kept) or replacement


def sanitize_numeric_prose(response: AgentSynthesis) -> AgentSynthesis:
    """Remove numeric prose while retaining safe qualitative statements."""

    response.answer = _strip_numeric_sentences(
        response.answer, "See the structured findings for supported operational values."
    )
    response.summary = _strip_numeric_sentences(
        response.summary, "Evidence-backed operational summary."
    )
    for finding in response.findings:
        finding.title = _strip_numeric_sentences(finding.title, "Operational finding")
        finding.description = _strip_numeric_sentences(
            finding.description, "See the structured evidence values."
        )
    for action in response.recommended_actions:
        action.title = _strip_numeric_sentences(action.title, "Review evidence")
        action.description = _strip_numeric_sentences(
            action.description, "Review the cited evidence before acting."
        )
    for reference in response.evidence:
        reference.description = _strip_numeric_sentences(
            reference.description, "Deterministic aggregate evidence."
        )
    response.data_quality_warnings = []
    return response


def validate_response_evidence(
    response: AgentResponse | AgentSynthesis,
    evidence: dict[str, Any],
    tolerance: float = 1e-4,
) -> None:
    """Validate every operational number against one stable evidence record."""

    indexed = _evidence_index(evidence)
    supported_tools = set(evidence)
    for index, reference in enumerate(response.evidence):
        if reference.tool not in supported_tools:
            raise _fail(
                f"evidence[{index}].tool",
                reference.tool,
                "tool_reference_must_exist",
            )

    has_numeric_finding = False
    for index, finding in enumerate(response.findings):
        claims = {
            "current_value": finding.current_value,
            "baseline_value": finding.baseline_value,
            "change": finding.change,
            "relative_change_pct": finding.relative_change_pct,
            "sample_size": finding.sample_size,
        }
        populated = {role: value for role, value in claims.items() if value is not None}
        has_numeric_finding = has_numeric_finding or bool(populated)
        if not populated:
            continue
        if not finding.evidence_id:
            raise _fail(
                f"findings[{index}].evidence_id",
                finding.evidence_id,
                "numeric_finding_requires_evidence_id",
            )
        record = indexed.get(finding.evidence_id)
        if record is None:
            raise _fail(
                f"findings[{index}].evidence_id",
                finding.evidence_id,
                "evidence_id_must_exist",
            )
        if finding.metric != record.metric:
            raise _fail(
                f"findings[{index}].metric",
                finding.metric,
                "metric_must_match_evidence_id",
                record.metric,
            )
        if finding.entity and finding.entity not in record.entities:
            nearest_entity = sorted(record.entities)[0] if record.entities else None
            raise _fail(
                f"findings[{index}].entity",
                finding.entity,
                "entity_must_match_evidence_id",
                nearest_entity,
            )
        for role, claim in populated.items():
            supported = record.values.get(role)
            if supported is None or not math.isclose(
                float(claim), supported, rel_tol=tolerance, abs_tol=tolerance
            ):
                raise _fail(
                    f"findings[{index}].{role}",
                    claim,
                    "value_must_match_evidence_id",
                    supported,
                )
    if not has_numeric_finding:
        raise _fail(
            "findings",
            None,
            "at_least_one_supported_numeric_finding_required",
        )

    narrative_fields = [response.answer, response.summary]
    narrative_fields.extend(
        text
        for finding in response.findings
        for text in (finding.title, finding.description)
    )
    narrative_fields.extend(
        text
        for action in response.recommended_actions
        for text in (action.title, action.description)
    )
    narrative_fields.extend(reference.description for reference in response.evidence)
    for index, text in enumerate(narrative_fields):
        match = NUMERIC_TEXT.search(text)
        if match:
            raise _fail(
                f"narrative[{index}]",
                match.group(0),
                "operational_numbers_belong_in_structured_fields",
            )
        lowered = text.lower()
        for phrase in (
            "statistically significant",
            "systemic impact",
            "service threshold",
            "sla threshold",
            "driver misconduct",
        ):
            if phrase in lowered:
                raise _fail(
                    f"narrative[{index}]",
                    phrase,
                    "unsupported_operational_claim",
                )
