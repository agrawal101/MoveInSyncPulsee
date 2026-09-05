from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from app.agents.graph import MobilityAgentGraph
from app.llm.provider import LLMProvider
from app.models.agent import (
    AgentQueryRequest,
    AgentResponse,
    ExecutiveSummaryRequest,
    ExecutionMetadata,
    InvestigationRequest,
)

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(
        self,
        provider: LLMProvider,
        database_path: Path = Path("data/processed/mobility.duckdb"),
    ) -> None:
        self.provider = provider
        self.database_path = database_path
        self.graph = MobilityAgentGraph(provider)

    def _run(
        self,
        *,
        endpoint: str,
        mode: str,
        question: str,
        month: str,
        baseline_month: str | None = None,
        anomaly_id: str | None = None,
    ) -> AgentResponse:
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        logger.info(
            "agent_execution_start",
            extra={"request_id": request_id, "endpoint": endpoint, "workflow": mode},
        )
        try:
            state = self.graph.graph.invoke(
                {
                    "request_id": request_id,
                    "endpoint": endpoint,
                    "mode": mode,
                    "question": question,
                    "month": month,
                    "baseline_month": baseline_month,
                    "anomaly_id": anomaly_id,
                    "started_at": started,
                }
            )
            response: AgentResponse = state["response"]
            response.data_quality_warnings = list(
                dict.fromkeys(
                    response.data_quality_warnings + state.get("warnings", [])
                )
            )
            response.execution = ExecutionMetadata(
                request_id=request_id,
                tools_called=state.get("tools_called", []),
                tool_durations_ms=state.get("tool_durations_ms", {}),
                llm_duration_ms=state.get("llm_duration_ms"),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                provider=state.get("llm_provider"),
                model=state.get("llm_model"),
                input_tokens=state.get("input_tokens"),
                output_tokens=state.get("output_tokens"),
                fallback_used=state.get("fallback_used", False),
                error_category=state.get("provider_error_category"),
                repair_attempted=state.get("repair_attempted", False),
                validator_rejection=state.get("validator_rejection"),
                validation_result=state.get("validation_result", "passed"),
            )
            logger.info(
                "agent_execution_complete",
                extra={
                    "request_id": request_id,
                    "endpoint": endpoint,
                    "workflow": mode,
                    "duration_ms": response.execution.duration_ms,
                    "provider": response.execution.provider,
                    "model": response.execution.model,
                    "input_tokens": response.execution.input_tokens,
                    "output_tokens": response.execution.output_tokens,
                    "fallback_used": response.execution.fallback_used,
                    "validation_result": response.execution.validation_result,
                    "error_category": response.execution.error_category,
                },
            )
            return response
        except Exception as exc:
            logger.exception(
                "agent_execution_error",
                extra={
                    "request_id": request_id,
                    "endpoint": endpoint,
                    "workflow": mode,
                    "error_category": type(exc).__name__,
                },
            )
            raise

    def query(self, request: AgentQueryRequest) -> AgentResponse:
        return self._run(
            endpoint="agent.query",
            mode="query",
            question=request.question,
            month=request.month,
            baseline_month=request.baseline_month,
        )

    def investigate(self, request: InvestigationRequest) -> AgentResponse:
        return self._run(
            endpoint="agent.investigate",
            mode="investigate",
            question=f"Investigate anomaly {request.anomaly_id}",
            month=request.month,
            anomaly_id=request.anomaly_id,
        )

    def executive_summary(self, request: ExecutiveSummaryRequest) -> AgentResponse:
        return self._run(
            endpoint="reports.executive_summary",
            mode="report",
            question=(
                "Create a leadership-ready executive summary with key risks, positive "
                "developments, recommended priorities, and a data-quality/confidence note."
            ),
            month=request.month,
            baseline_month=request.baseline_month,
        )
