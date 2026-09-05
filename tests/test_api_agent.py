from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.agents.service import AgentService
from app.agents.tools import get_monthly_overview_tool
from app.analytics.anomaly_detection import detect_anomalies
from app.api.deps import get_agent_service
from app.llm.provider import LLMProvider, LLMResult
from app.main import app
from app.models.agent import (
    AgentFinding,
    EvidenceReference,
    GroundedAgentFinding,
    RecommendedAction,
)


class FakeProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_structured(
        self,
        *,
        system_prompt: str,
        task: str,
        evidence: dict[str, Any],
        response_model: type[BaseModel],
        workflow: str,
    ) -> LLMResult:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "task": task,
                "evidence": evidence,
                "workflow": workflow,
            }
        )
        if "analyze_cost_tool" in evidence:
            source_tool = "analyze_cost_tool"
            metric = "billed_rows"
            current_value = evidence[source_tool][metric]
            evidence_id = evidence[source_tool]["evidence_ids"][metric]
            baseline_value = change = sample_size = None
        elif "get_monthly_overview_tool" in evidence:
            source_tool = "get_monthly_overview_tool"
            metric = "total_trips"
            item = evidence[source_tool]["metrics"][metric]
            evidence_id = item["evidence_id"]
            current_value = item["current_value"]
            baseline_value = item["baseline_value"]
            change = item["absolute_change"]
            sample_size = item["sample_size"]
        else:
            source_tool = "detect_anomalies_tool"
            item = evidence["selected_anomaly"]
            evidence_id = item["evidence_id"]
            metric = item["metric"]
            current_value = item["current_value"]
            baseline_value = item["baseline_value"]
            change = item["absolute_change"]
            sample_size = item["sample_size"]
        response = response_model(
            answer="Evidence-backed answer.",
            summary="Deterministic evidence summarized.",
            severity="high",
            confidence="high",
            synthesis_mode="llm",
            findings=[
                GroundedAgentFinding(
                    title="Observed finding",
                    description="Finding comes from deterministic tool evidence.",
                    evidence_id=evidence_id,
                    metric=metric,
                    current_value=current_value,
                    baseline_value=baseline_value,
                    change=change,
                    sample_size=sample_size,
                )
            ],
            recommended_actions=[
                RecommendedAction(
                    title="Review operations",
                    description="Investigate supporting records.",
                )
            ],
            evidence=[
                EvidenceReference(
                    tool=source_tool,
                    description="Deterministic analytics output",
                )
            ],
            data_quality_warnings=[],
        )
        return LLMResult(
            output=response,
            model="fake-structured-model",
            latency_ms=4.5,
            input_tokens=120,
            output_tokens=45,
        )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_health_and_deterministic_overview(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200
    response = client.get("/api/overview", params={"month": "2026-07"})
    assert response.status_code == 200
    assert response.json()["metrics"]["total_trips"]["current_value"] == 215885


def test_invalid_month_and_vendor(client: TestClient) -> None:
    assert client.get("/api/overview", params={"month": "2099-01"}).status_code == 422
    response = client.get(
        "/api/vendors/missing-vendor",
        params={"month": "2026-07", "baseline_month": "2026-06"},
    )
    assert response.status_code == 422


def test_anomaly_endpoint_filter(client: TestClient) -> None:
    response = client.get(
        "/api/anomalies",
        params={"month": "2026-07", "severity": "high", "limit": 2},
    )
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert all(row["severity"] == "high" for row in response.json())


def test_tool_wrapper_returns_existing_analytics() -> None:
    result = get_monthly_overview_tool.invoke({"month": "2026-07"})
    assert result["metrics"]["total_trips"]["current_value"] == 215885


def test_missing_llm_configuration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    response = client.post(
        "/api/agent/query",
        json={"question": "What changed in July?", "month": "2026-07"},
    )
    assert response.status_code == 503
    assert response.json()["error"] == "llm_not_configured"


def test_mocked_llm_and_warning_propagation(client: TestClient) -> None:
    provider = FakeProvider()
    app.dependency_overrides[get_agent_service] = lambda: AgentService(provider)
    try:
        response = client.post(
            "/api/agent/query",
            json={
                "question": "Are July cost-per-km metrics reliable?",
                "month": "2026-07",
                "baseline_month": "2026-06",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "analyze_cost_tool" in body["execution"]["tools_called"]
        assert any("excluded" in warning for warning in body["data_quality_warnings"])
        assert body["synthesis_mode"] == "llm"
        assert body["execution"]["model"] == "fake-structured-model"
        assert body["execution"]["input_tokens"] == 120
        assert body["execution"]["fallback_used"] is False
        assert provider.calls
    finally:
        app.dependency_overrides.clear()


def test_investigation_workflow_and_not_found(client: TestClient) -> None:
    provider = FakeProvider()
    app.dependency_overrides[get_agent_service] = lambda: AgentService(provider)
    try:
        anomaly = detect_anomalies("2026-07")[0]
        response = client.post(
            "/api/agent/investigate",
            json={"anomaly_id": anomaly.id, "month": "2026-07"},
        )
        assert response.status_code == 200
        assert "detect_anomalies_tool" in response.json()["execution"]["tools_called"]
        missing = client.post(
            "/api/agent/investigate",
            json={"anomaly_id": "missing", "month": "2026-07"},
        )
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_executive_summary_evidence_assembly(client: TestClient) -> None:
    provider = FakeProvider()
    app.dependency_overrides[get_agent_service] = lambda: AgentService(provider)
    try:
        response = client.post(
            "/api/reports/executive-summary",
            json={"month": "2026-07", "baseline_month": "2026-06"},
        )
        assert response.status_code == 200
        keys = provider.calls[0]["evidence"]
        assert {
            "get_monthly_overview_tool",
            "detect_anomalies_tool",
            "analyze_safety_alerts_tool",
            "analyze_cost_tool",
        } <= set(keys)
    finally:
        app.dependency_overrides.clear()
