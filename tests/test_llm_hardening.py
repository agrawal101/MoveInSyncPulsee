from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.evidence import attach_evidence_ids, compact_evidence
from app.agents.service import AgentService
from app.agents.validation import UnsupportedEvidenceError, validate_response_evidence
from app.analytics.anomaly_detection import detect_anomalies
from app.api.deps import get_agent_service
from app.llm.provider import (
    AnthropicProvider,
    FallbackProvider,
    LLMAuthenticationError,
    LLMProvider,
    LLMProviderChainError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseError,
    LLMResult,
    LLMTimeoutError,
    OpenAIProvider,
    SarvamProvider,
)
from app.main import app
from app.models.agent import (
    AgentFinding,
    AgentResponse,
    AgentSynthesis,
    EvidenceReference,
    GroundedAgentFinding,
    RecommendedAction,
)


def _agent_response(answer: str = "Grounded response") -> AgentSynthesis:
    return AgentSynthesis(
        answer=answer,
        summary=answer,
        severity="informational",
        confidence="high",
        synthesis_mode="llm",
        findings=[
            GroundedAgentFinding(
                title="Observed metric",
                description="Value supplied by deterministic evidence.",
                evidence_id="ev_overview_count",
                metric="count",
                current_value=1,
            )
        ],
        recommended_actions=[
            RecommendedAction(
                title="Review evidence",
                description="Use the cited result for follow-up.",
            )
        ],
        evidence=[EvidenceReference(tool="overview", description="Approved evidence")],
        data_quality_warnings=[],
    )


def _sarvam_body(content: str, model: str = "sarvam-105b") -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 101, "completion_tokens": 31, "total_tokens": 132},
    }


def _sarvam_provider(handler: Any) -> SarvamProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.sarvam.ai",
        timeout=1,
    )
    return SarvamProvider("test-key", client=client)


class FailingProvider(LLMProvider):
    provider_name = "failing"

    def generate_structured(self, **_: Any) -> LLMResult:
        raise LLMProviderError("simulated provider outage")


class StaticProvider(LLMProvider):
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def generate_structured(self, **kwargs: Any) -> LLMResult:
        evidence = kwargs.get("evidence", {})
        overview = evidence.get("get_monthly_overview_tool", {}).get("metrics", {})
        total_trips = overview.get("total_trips")
        if total_trips:
            output = AgentSynthesis(
                answer="Volume is supported by deterministic evidence.",
                summary="Current mobility volume",
                severity="informational",
                confidence="high",
                synthesis_mode="llm",
                findings=[
                    GroundedAgentFinding(
                        title="Mobility volume",
                        description="Current volume is available for review.",
                        evidence_id=total_trips.get("evidence_id"),
                        metric="total_trips",
                        current_value=total_trips.get("current_value"),
                        baseline_value=total_trips.get("baseline_value"),
                        change=total_trips.get("absolute_change"),
                        sample_size=total_trips.get("sample_size"),
                    )
                ],
                recommended_actions=[
                    RecommendedAction(
                        title="Review volume movement",
                        description="Use the cited aggregate for operational follow-up.",
                    )
                ],
                evidence=[
                    EvidenceReference(
                        tool="get_monthly_overview_tool",
                        description="Approved monthly evidence",
                    )
                ],
                data_quality_warnings=[],
            )
        else:
            output = _agent_response()
        return LLMResult(
            output=output,
            provider=self.provider_name,
            model=f"{self.provider_name}-model",
            latency_ms=3,
            input_tokens=10,
            output_tokens=5,
        )


class UnsupportedNumberProvider(LLMProvider):
    provider_name = "bad"

    def __init__(self) -> None:
        self.calls = 0

    def generate_structured(self, **kwargs: Any) -> LLMResult:
        self.calls += 1
        evidence = kwargs["evidence"]
        first_tool = next(iter(evidence))
        total_trips = evidence.get("get_monthly_overview_tool", {}).get(
            "metrics", {}
        ).get("total_trips", {})
        output = AgentSynthesis(
            answer="Unsupported metric test.",
            summary="Unsupported metric test.",
            severity="high",
            confidence="high",
            synthesis_mode="llm",
            findings=[
                GroundedAgentFinding(
                    title="Invented KPI",
                    description="Must be rejected.",
                    evidence_id=total_trips.get("evidence_id"),
                    metric="total_trips",
                    current_value=999_999_999,
                )
            ],
            recommended_actions=[
                RecommendedAction(
                    title="Review evidence",
                    description="Use deterministic evidence only.",
                )
            ],
            evidence=[EvidenceReference(tool=first_tool, description="Tool evidence")],
            data_quality_warnings=[],
        )
        return LLMResult(
            output=output,
            provider=self.provider_name,
            model="bad-model",
            latency_ms=1,
        )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_sarvam_uses_v1_strict_schema_and_conservative_settings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "sarvam-105b"
        assert payload["temperature"] == 0.2
        assert payload["reasoning_effort"] is None
        assert payload["stream"] is False
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["response_format"]["json_schema"]["schema"]["type"] == "object"
        return httpx.Response(200, json=_sarvam_body(_agent_response().model_dump_json()))

    result = _sarvam_provider(handler).generate_structured(
        system_prompt="Use evidence.",
        task="Summarize.",
        evidence={"overview": {"count": 1}},
        response_model=AgentSynthesis,
        workflow="query",
    )
    assert result.provider == "sarvam"
    assert result.model == "sarvam-105b"
    assert result.input_tokens == 101
    assert result.output_tokens == 31


def test_sarvam_invalid_key_is_typed_and_not_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, json={"error": {"code": "invalid_api_key_error"}})

    with pytest.raises(LLMAuthenticationError):
        _sarvam_provider(handler).generate_structured(
            system_prompt="Test",
            task="Test",
            evidence={},
            response_model=AgentSynthesis,
            workflow="query",
        )
    assert calls == 1


def test_sarvam_timeout_retries_once_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("simulated timeout", request=request)
        return httpx.Response(200, json=_sarvam_body(_agent_response().model_dump_json()))

    result = _sarvam_provider(handler).generate_structured(
        system_prompt="Test",
        task="Test",
        evidence={},
        response_model=AgentSynthesis,
        workflow="query",
    )
    assert result.output.answer == "Grounded response"
    assert calls == 2


def test_sarvam_rate_limit_retries_once_then_raises() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": {"code": "quota_exceeded"}})

    with pytest.raises(LLMRateLimitError):
        _sarvam_provider(handler).generate_structured(
            system_prompt="Test",
            task="Test",
            evidence={},
            response_model=AgentSynthesis,
            workflow="query",
        )
    assert calls == 2


def test_sarvam_malformed_output_gets_one_repair() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json=_sarvam_body('{"answer":"incomplete"}'))
        payload = json.loads(request.content)
        assert "failed schema validation" in payload["messages"][1]["content"]
        return httpx.Response(200, json=_sarvam_body(_agent_response("Repaired").model_dump_json()))

    result = _sarvam_provider(handler).generate_structured(
        system_prompt="Test",
        task="Test",
        evidence={},
        response_model=AgentSynthesis,
        workflow="query",
    )
    assert result.output.answer == "Repaired"
    assert calls == 2
    assert result.validation_result == "repaired"


def test_sarvam_malformed_output_twice_raises() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_sarvam_body("not-json"))

    with pytest.raises(LLMResponseError):
        _sarvam_provider(handler).generate_structured(
            system_prompt="Test",
            task="Test",
            evidence={},
            response_model=AgentSynthesis,
            workflow="query",
        )
    assert calls == 2


def test_openai_provider_fallback_metadata() -> None:
    chain = FallbackProvider(FailingProvider(), StaticProvider("openai"))
    result = chain.generate_structured(
        system_prompt="Test",
        task="Test",
        evidence={},
        response_model=AgentResponse,
        workflow="query",
    )
    assert result.provider == "openai"
    assert result.fallback_used is True
    assert result.error_category == "LLMProviderError"


def test_api_exposes_provider_and_validation_metadata(client: TestClient) -> None:
    app.dependency_overrides[get_agent_service] = lambda: AgentService(
        StaticProvider("sarvam")
    )
    try:
        response = client.post(
            "/api/agent/query",
            json={"question": "What changed in July?", "month": "2026-07"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["synthesis_mode"] == "llm"
        assert body["execution"]["provider"] == "sarvam"
        assert body["execution"]["model"] == "sarvam-model"
        assert body["execution"]["fallback_used"] is False
        assert body["execution"]["validation_result"] == "passed"
    finally:
        app.dependency_overrides.clear()


def test_both_providers_failing_uses_deterministic_fallback(client: TestClient) -> None:
    chain = FallbackProvider(FailingProvider(), FailingProvider())
    app.dependency_overrides[get_agent_service] = lambda: AgentService(chain)
    try:
        response = client.post(
            "/api/agent/query",
            json={"question": "What changed in July?", "month": "2026-07"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["synthesis_mode"] == "deterministic_fallback"
        assert body["execution"]["validation_result"] == "deterministic_fallback"
        assert body["execution"]["error_category"] == "LLMProviderChainError"
    finally:
        app.dependency_overrides.clear()


def test_provider_chain_raises_typed_error_when_both_fail() -> None:
    chain = FallbackProvider(FailingProvider(), FailingProvider())
    with pytest.raises(LLMProviderChainError):
        chain.generate_structured(
            system_prompt="Test",
            task="Test",
            evidence={},
            response_model=AgentResponse,
            workflow="query",
        )


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/agent/query",
            {"question": "What changed in July?", "month": "2026-07"},
        ),
        (
            "/api/reports/executive-summary",
            {"month": "2026-07", "baseline_month": "2026-06"},
        ),
    ],
)
def test_provider_failure_returns_deterministic_fallback(
    client: TestClient, path: str, payload: dict[str, str]
) -> None:
    app.dependency_overrides[get_agent_service] = lambda: AgentService(FailingProvider())
    try:
        response = client.post(path, json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["synthesis_mode"] == "deterministic_fallback"
        assert body["execution"]["fallback_used"] is True
        assert body["execution"]["error_category"] == "LLMProviderError"
        assert body["evidence"]
        assert any(
            "analytics-backed" in warning for warning in body["data_quality_warnings"]
        )
    finally:
        app.dependency_overrides.clear()


def test_investigation_provider_failure_returns_targeted_fallback(
    client: TestClient,
) -> None:
    anomaly = next(
        item
        for item in detect_anomalies("2026-07")
        if item.entity_name == "Aarav Petrov Travel"
        and item.metric == "alerts_per_1000_trips"
    )
    app.dependency_overrides[get_agent_service] = lambda: AgentService(FailingProvider())
    try:
        response = client.post(
            "/api/agent/investigate",
            json={"anomaly_id": anomaly.id, "month": "2026-07"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["synthesis_mode"] == "deterministic_fallback"
        assert body["findings"][0]["metric"] == "alerts_per_1000_trips"
        assert body["findings"][0]["current_value"] == anomaly.current_value
        assert body["findings"][0]["sample_size"] == anomaly.sample_size
    finally:
        app.dependency_overrides.clear()


def test_vendor_query_provider_failure_keeps_useful_risk_story(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_agent_service] = lambda: AgentService(FailingProvider())
    try:
        response = client.post(
            "/api/agent/query",
            json={
                "question": "Why is Aarav Petrov Travel high risk?",
                "month": "2026-07",
                "baseline_month": "2026-06",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "targeted safety investigation" in body["summary"]
        assert body["findings"][0]["metric"] == "alerts_per_1000_trips"
        assert any(item["metric"] == "no_show_rate" for item in body["findings"])
    finally:
        app.dependency_overrides.clear()


def test_demo_mode_without_key_returns_current_evidence_fallback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    response = client.post(
        "/api/agent/query",
        json={"question": "Which shift needs attention?", "month": "2026-07"},
    )
    assert response.status_code == 200
    assert response.json()["synthesis_mode"] == "deterministic_fallback"


def test_unsupported_model_number_gets_one_repair_then_fallback(
    client: TestClient,
) -> None:
    provider = UnsupportedNumberProvider()
    app.dependency_overrides[get_agent_service] = lambda: AgentService(provider)
    try:
        response = client.post(
            "/api/agent/query",
            json={"question": "What changed in July?", "month": "2026-07"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["synthesis_mode"] == "deterministic_fallback"
        assert body["execution"]["error_category"] == "UnsupportedEvidenceError"
        assert provider.calls == 2
    finally:
        app.dependency_overrides.clear()


def test_validator_requires_metric_specific_values_and_sample() -> None:
    evidence = {
        "overview": {
            "metrics": {
                "total_trips": {"current_value": 100, "sample_size": 100},
                "delay_rate": {"current_value": 7.5, "sample_size": 90},
            }
        }
    }
    response = AgentResponse(
        answer="Test",
        summary="Test",
        severity="medium",
        confidence="high",
        findings=[
            AgentFinding(
                title="Wrong mapping",
                description="Values belong to another metric.",
                metric="delay_rate",
                current_value=100,
                sample_size=100,
            )
        ],
        evidence=[EvidenceReference(tool="overview", description="Overview")],
    )
    with pytest.raises(UnsupportedEvidenceError):
        validate_response_evidence(response, evidence)


def test_validator_rejects_numeric_claims_hidden_in_narrative() -> None:
    evidence = attach_evidence_ids({"overview": {"count": 20}})
    response = AgentResponse(
        answer="This category represents 55% of delay.",
        summary="Unsupported calculation",
        severity="medium",
        confidence="high",
        findings=[
            AgentFinding(
                title="Observed count",
                description="Count comes from evidence.",
                evidence_id=evidence["overview"]["evidence_ids"]["count"],
                metric="count",
                current_value=20,
            )
        ],
        evidence=[EvidenceReference(tool="overview", description="Overview")],
    )
    with pytest.raises(
        UnsupportedEvidenceError,
        match="operational_numbers_belong_in_structured_fields",
    ):
        validate_response_evidence(response, evidence)


def test_evidence_ids_are_stable_and_bind_metric_values() -> None:
    source = {
        "analyze_vendor_tool": {
            "vendor": "Aarav Petrov Travel",
            "month": "2026-07",
            "metrics": {
                "alert_rate": {
                    "metric": "alert_rate",
                    "current_value": 12.5,
                    "baseline_value": 10.0,
                    "absolute_change": 2.5,
                    "sample_size": 100,
                }
            },
        }
    }
    first = attach_evidence_ids(source)
    second = attach_evidence_ids(source)
    metric = first["analyze_vendor_tool"]["metrics"]["alert_rate"]
    assert metric["evidence_id"] == second["analyze_vendor_tool"]["metrics"]["alert_rate"]["evidence_id"]
    response = AgentResponse(
        answer="Alert frequency worsened.",
        summary="Vendor safety needs review.",
        severity="informational",
        confidence="high",
        findings=[
            AgentFinding(
                title="Alert rate increased",
                description="The observed rate is above its baseline.",
                evidence_id=metric["evidence_id"],
                entity="Aarav Petrov Travel",
                metric="alert_rate",
                current_value=12.5,
                baseline_value=10.0,
                change=2.5,
                sample_size=100,
            )
        ],
        evidence=[
            EvidenceReference(
                tool="analyze_vendor_tool", description="Vendor evidence"
            )
        ],
    )
    validate_response_evidence(response, first)


def test_provider_schema_excludes_runtime_execution_metadata() -> None:
    schema = AgentSynthesis.model_json_schema()
    assert "execution" not in schema["properties"]
    assert "ExecutionMetadata" not in schema.get("$defs", {})
    assert schema["properties"]["findings"]["minItems"] == 1


def test_context_compaction_excludes_trip_rows_and_is_bounded() -> None:
    evidence = {
        "detect_anomalies_tool": [
            {"severity": "high", "id": f"high-{index}"} for index in range(20)
        ]
        + [{"severity": "positive", "id": f"good-{index}"} for index in range(10)],
        "analyze_delay_causes_tool": {
            "reasons": [{"name": "traffic", "count": 20}],
            "trip_evidence": [{"trip_id": str(index)} for index in range(100)],
        },
        "get_data_quality_report_tool": {
            "preprocessing": {"large": "x" * 20_000},
            "warnings": ["quality warning"],
        },
        "raw_trips_tool": [{"trip_id": "must-not-pass"}],
    }
    compact = compact_evidence(evidence)
    assert len(compact["detect_anomalies_tool"]) == 9
    assert "trip_evidence" not in compact["analyze_delay_causes_tool"]
    assert "preprocessing" not in compact["get_data_quality_report_tool"]
    assert "raw_trips_tool" not in compact
    assert len(json.dumps(compact)) < len(json.dumps(evidence))


def test_openai_provider_repairs_one_malformed_structured_response() -> None:
    parsed = _agent_response("Repaired")

    class Responses:
        def __init__(self) -> None:
            self.calls = 0

        def parse(self, **_: Any) -> SimpleNamespace:
            self.calls += 1
            return SimpleNamespace(
                output_parsed=None if self.calls == 1 else parsed,
                usage=SimpleNamespace(input_tokens=21, output_tokens=8),
            )

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = SimpleNamespace(responses=Responses())
    provider.model = "test-model"
    result = provider.generate_structured(
        system_prompt="Use evidence.",
        task="Summarize.",
        evidence={"overview": {"count": 1}},
        response_model=AgentSynthesis,
        workflow="query",
    )
    assert result.output.answer == "Repaired"
    assert provider.client.responses.calls == 2
    assert result.provider == "openai"
    assert result.input_tokens == 21
    assert result.validation_result == "repaired"


def test_openai_timeout_is_mapped_to_typed_error() -> None:
    from openai import APITimeoutError

    class Responses:
        def parse(self, **_: Any) -> None:
            raise APITimeoutError(request=httpx.Request("POST", "https://api.openai.com"))

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = SimpleNamespace(responses=Responses())
    provider.model = "test-model"
    with pytest.raises(LLMTimeoutError):
        provider.generate_structured(
            system_prompt="Use evidence.",
            task="Summarize.",
            evidence={"overview": {"count": 1}},
            response_model=AgentSynthesis,
            workflow="query",
        )


def test_anthropic_messages_parse_returns_structured_metadata() -> None:
    class Messages:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def parse(self, **kwargs: Any) -> SimpleNamespace:
            self.calls.append(kwargs)
            return SimpleNamespace(
                parsed_output=_agent_response(),
                model="claude-sonnet-5",
                usage=SimpleNamespace(input_tokens=321, output_tokens=87),
            )

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = SimpleNamespace(messages=Messages())
    provider.model = "claude-sonnet-5"
    evidence = compact_evidence(
        {
            "analyze_delay_causes_tool": {
                "reasons": [{"delay_reason": "TRAFFIC", "trip_count": 20}],
                "trip_evidence": [{"trip_id": "must-not-send"}],
            }
        }
    )
    result = provider.generate_structured(
        system_prompt="Use evidence only.",
        task="Summarize delay.",
        evidence=evidence,
        response_model=AgentSynthesis,
        workflow="query",
    )
    call = provider.client.messages.calls[0]
    assert call["output_format"] is AgentSynthesis
    assert call["model"] == "claude-sonnet-5"
    assert call["system"] == "Use evidence only."
    assert "must-not-send" not in call["messages"][0]["content"]
    assert result.provider == "anthropic"
    assert result.model == "claude-sonnet-5"
    assert result.input_tokens == 321
    assert result.output_tokens == 87
    assert result.validation_result == "passed"


def test_anthropic_malformed_output_gets_one_bounded_repair() -> None:
    parsed = _agent_response("Claude repaired response")

    class Messages:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def parse(self, **kwargs: Any) -> SimpleNamespace:
            self.calls.append(kwargs)
            return SimpleNamespace(
                parsed_output=None if len(self.calls) == 1 else parsed,
                model="claude-sonnet-5",
                usage=SimpleNamespace(input_tokens=222, output_tokens=66),
            )

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = SimpleNamespace(messages=Messages())
    provider.model = "claude-sonnet-5"
    result = provider.generate_structured(
        system_prompt="Use evidence only.",
        task="Summarize.",
        evidence={"overview": {"count": 1}},
        response_model=AgentSynthesis,
        workflow="query",
    )
    assert len(provider.client.messages.calls) == 2
    repair_prompt = provider.client.messages.calls[1]["messages"][0]["content"]
    assert "Repair the previous response once" in repair_prompt
    assert result.output.answer == "Claude repaired response"
    assert result.validation_result == "repaired"
