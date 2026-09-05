#!/usr/bin/env python3
"""Explicit live-provider smoke suite. This file is not collected by pytest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app


QUESTIONS = [
    "Why is Aarav Petrov Travel high risk?",
    "What improved in July?",
    "Which shift should operations investigate first?",
    "What caused most delays in July?",
    "Are July cost-per-km metrics reliable?",
]


def _preflight() -> None:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in {"sarvam", "openai", "anthropic"}:
        raise SystemExit(
            "Set LLM_PROVIDER to sarvam, openai, or anthropic before running live calls."
        )
    key_name = {
        "sarvam": "SARVAM_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }[provider]
    if not os.getenv(key_name, "").strip():
        raise SystemExit(f"Set {key_name} before running live calls.")
    if os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower() == "openai":
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise SystemExit("Set OPENAI_API_KEY for the configured fallback provider.")


def _capture(label: str, response: Any) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text[:500]}
    execution = body.get("execution") or {}
    return {
        "label": label,
        "status_code": response.status_code,
        "synthesis_mode": body.get("synthesis_mode"),
        "provider": execution.get("provider"),
        "model": execution.get("model"),
        "latency_ms": execution.get("duration_ms"),
        "llm_latency_ms": execution.get("llm_duration_ms"),
        "input_tokens": execution.get("input_tokens"),
        "output_tokens": execution.get("output_tokens"),
        "fallback_used": execution.get("fallback_used"),
        "repair_attempted": execution.get("repair_attempted", False),
        "validation_result": execution.get("validation_result"),
        "validator_rejection": execution.get("validator_rejection"),
        "tools_called": execution.get("tools_called", []),
        "summary": body.get("summary"),
        "answer": body.get("answer"),
        "findings": body.get("findings", []),
        "recommended_actions": body.get("recommended_actions", []),
        "data_quality_warnings": body.get("data_quality_warnings", []),
        "error": body.get("detail") if response.status_code >= 400 else None,
    }


def run() -> int:
    parser = argparse.ArgumentParser(description="Run explicit live LLM workflow checks.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/live_llm_results.json"),
    )
    args = parser.parse_args()
    _preflight()
    client = TestClient(app, raise_server_exceptions=False)
    results: list[dict[str, Any]] = []

    for question in QUESTIONS:
        response = client.post(
            "/api/agent/query",
            json={
                "question": question,
                "month": "2026-07",
                "baseline_month": "2026-06",
            },
        )
        results.append(_capture(question, response))

    report = client.post(
        "/api/reports/executive-summary",
        json={"month": "2026-07", "baseline_month": "2026-06"},
    )
    results.append(_capture("July executive summary", report))

    payload = {
        "primary_provider": os.getenv("LLM_PROVIDER"),
        "fallback_provider": os.getenv("LLM_FALLBACK_PROVIDER") or None,
        "sarvam_model": os.getenv("SARVAM_MODEL", "sarvam-105b"),
        "openai_model": os.getenv("OPENAI_MODEL") or None,
        "anthropic_model": os.getenv("ANTHROPIC_MODEL") or None,
        "settings": {
            "timeout_seconds": float(os.getenv("LLM_TIMEOUT_SECONDS", "18")),
            "sarvam_temperature": 0.2,
            "sarvam_reasoning_effort": None,
            "provider_retry_limit": 1,
            "validation_repair_limit": 1,
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))

    failed = [
        item
        for item in results
        if item["status_code"] != 200 or item["synthesis_mode"] != "llm"
    ]
    if failed:
        print(
            f"Live verification incomplete: {len(failed)} request(s) did not use an LLM.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
