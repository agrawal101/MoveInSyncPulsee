from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.graph import MobilityAgentGraph
from app.analytics.anomaly_detection import detect_anomalies
from app.analytics.cross_domain_anomalies import (
    MIN_BILL_ROWS,
    MIN_VENDOR_TRIPS,
    CrossDomainAnomalyEngine,
    detect_cross_domain_anomalies,
)
from app.llm.factory import UnavailableProvider
from app.main import app

DB = Path("data/processed/mobility.duckdb")
BANNED = ("fraud detected", "confirmed fraud", "committed fraud", "proven fraud", "fraudster")


def _base_signal(**overrides) -> dict:
    """A deterministically 'normal' vendor signal; tests mutate single fields."""
    signal = {
        "vendor": "Test Vendor",
        "trips": 5000,
        "trip_volume_change_pct": 1.0,
        "total_cost": 100000.0,
        "billing_change_pct": 1.0,
        "cost_per_valid_km": 80.0,
        "cost_per_valid_km_change": 0.0,
        "valid_cost_km_coverage": 99.0,
        "no_show_rate": 0.03,
        "no_show_change": 0.0,
        "delay_rate": 0.08,
        "delay_rate_change": 0.0,
        "average_delay": 12.0,
        "safety_alerts_per_1000_trips": 60.0,
        "safety_alert_rate_change": 0.0,
        "safety_alert_rate_rel": 0.0,
        "experience_rating": 4.8,
        "experience_rating_change": 0.0,
        "utilization": 0.60,
        "utilization_change": 0.0,
        "zero_distance_billing_rate": 1.0,
        "negative_distance_count": 0,
        "missing_join_count": 0,
        "bill_rows": 5000,
        "peer_rank": 3,
        "_peers": {
            "cost_per_valid_km": 80.0,
            "safety_alerts_per_1000_trips": 60.0,
            "no_show_rate": 0.03,
            "delay_rate": 0.08,
            "zero_distance_billing_rate": 5.0,
        },
        "_baseline_month": "2026-06",
        "_month": "2026-07",
    }
    signal.update(overrides)
    return signal


engine = CrossDomainAnomalyEngine(DB)


# --- Threshold / multi-signal logic (no DB required) -------------------------

def test_billing_multi_signal_generates_anomaly_and_conservative_wording() -> None:
    anomaly = engine._billing_integrity(
        _base_signal(billing_change_pct=10.0, valid_cost_km_coverage=20.0)
    )
    assert anomaly is not None
    assert anomaly.category == "billing_integrity"
    assert anomaly.title == "Potential billing irregularity"
    assert "reconciliation" in anomaly.why_flagged.lower()
    text = (anomaly.why_flagged + " ".join(anomaly.recommended_investigation)).lower()
    assert not any(phrase in text for phrase in BANNED)
    assert len(anomaly.signals) >= 2  # billing + coverage at minimum


def test_no_anomaly_when_single_weak_signal_moves() -> None:
    # Billing rose but proportionately with trips, coverage healthy: not an anomaly.
    assert engine._billing_integrity(
        _base_signal(billing_change_pct=6.0, trip_volume_change_pct=6.0)
    ) is None
    # A tiny safety wobble under threshold does not flag.
    assert engine._safety_pattern(
        _base_signal(safety_alert_rate_change=3.0, safety_alert_rate_rel=5.0)
    ) is None


def test_safety_divergence_requires_service_to_hold_or_improve() -> None:
    diverges = engine._safety_pattern(
        _base_signal(
            safety_alert_rate_change=40.0, safety_alert_rate_rel=50.0,
            no_show_change=-0.03, delay_rate_change=-0.02,
        )
    )
    assert diverges is not None and diverges.category == "safety_pattern"
    # If service ALSO deteriorates it is broad decline, not a divergence.
    assert engine._safety_pattern(
        _base_signal(
            safety_alert_rate_change=40.0, safety_alert_rate_rel=50.0,
            no_show_change=0.05,
        )
    ) is None


def test_data_integrity_threshold_and_scale_gate() -> None:
    flagged = engine._data_integrity(
        _base_signal(zero_distance_billing_rate=95.0, bill_rows=6000)
    )
    assert flagged is not None and flagged.category == "data_integrity_anomaly"
    # Below concentration threshold -> nothing.
    assert engine._data_integrity(
        _base_signal(zero_distance_billing_rate=30.0, bill_rows=6000)
    ) is None
    # High rate but tiny scale -> nothing (business-impact gate).
    assert engine._data_integrity(
        _base_signal(zero_distance_billing_rate=95.0, bill_rows=MIN_BILL_ROWS - 1)
    ) is None


def test_risk_score_is_explainable_and_bounded() -> None:
    anomaly = engine._billing_integrity(
        _base_signal(billing_change_pct=12.0, valid_cost_km_coverage=10.0)
    )
    assert anomaly is not None
    assert 0.0 <= anomaly.cross_signal_risk_score <= 100.0
    assert {c.name for c in anomaly.risk_components} == {
        "historical_deviation", "correlated_signals", "peer_deviation", "data_confidence",
    }
    component_sum = round(sum(c.value for c in anomaly.risk_components), 1)
    # Score equals the (capped) sum of its published components.
    assert anomaly.cross_signal_risk_score == min(100.0, component_sum)
    assert all(c.detail for c in anomaly.risk_components)


# --- Real-data behaviour -----------------------------------------------------

@pytest.mark.skipif(not DB.exists(), reason="processed database unavailable")
def test_real_detection_multi_signal_and_sample_protection() -> None:
    results = detect_cross_domain_anomalies("2026-07", "2026-06", DB)
    assert results, "expected real cross-domain anomalies for July"
    # Every anomaly is multi-signal and above the sample-size floor.
    for a in results:
        assert len(a.signals) >= 1
        assert a.sample_size >= min(MIN_VENDOR_TRIPS, MIN_BILL_ROWS)
        assert a.id.startswith("cross-")
    # The strongest July pattern is a real safety divergence, not a fabricated one.
    top = results[0]
    assert top.category == "safety_pattern"
    assert len(top.signals) >= 2


@pytest.mark.skipif(not DB.exists(), reason="processed database unavailable")
def test_baseline_and_peer_comparison_present() -> None:
    results = detect_cross_domain_anomalies("2026-07", "2026-06", DB)
    assert any(s.baseline_value is not None for a in results for s in a.signals)
    assert any(s.peer_median is not None for a in results for s in a.signals)


@pytest.mark.skipif(not DB.exists(), reason="processed database unavailable")
def test_no_fraud_accusation_anywhere_in_real_output() -> None:
    results = detect_cross_domain_anomalies("2026-07", "2026-06", DB)
    blob = json.dumps([a.model_dump() for a in results]).lower()
    assert not any(phrase in blob for phrase in BANNED)
    # Billing anomalies must use reconciliation language.
    for a in results:
        if a.category == "billing_integrity":
            assert "reconciliation" in a.why_flagged.lower()


# --- API + backward compatibility -------------------------------------------

@pytest.mark.skipif(not DB.exists(), reason="processed database unavailable")
def test_cross_domain_api_output_and_filters() -> None:
    client = TestClient(app)
    r = client.get("/api/anomalies/cross-domain?month=2026-07&baseline_month=2026-06&limit=5")
    assert r.status_code == 200
    rows = r.json()
    assert rows
    required = {"id", "category", "entity_name", "title", "severity", "confidence",
               "cross_signal_risk_score", "signals", "why_flagged",
               "recommended_investigation", "risk_components"}
    assert required.issubset(rows[0].keys())
    # Category filter narrows the feed.
    billing = client.get("/api/anomalies/cross-domain?month=2026-07&category=billing_integrity").json()
    assert all(a["category"] == "billing_integrity" for a in billing)


@pytest.mark.skipif(not DB.exists(), reason="processed database unavailable")
def test_existing_anomaly_endpoint_unchanged_and_optional_merge() -> None:
    client = TestClient(app)
    legacy = client.get("/api/anomalies?month=2026-07&limit=5")
    assert legacy.status_code == 200
    assert all(a["id"].startswith("anomaly-") for a in legacy.json())
    # detect_anomalies itself is untouched.
    assert detect_anomalies("2026-07", DB)
    # Opt-in merge appends cross-domain items projected onto the Anomaly shape.
    merged = client.get("/api/anomalies?month=2026-07&include_cross_domain=true&limit=50").json()
    assert any(a["id"].startswith("cross-") for a in merged)
    assert any(a["id"].startswith("anomaly-") for a in merged)


@pytest.mark.skipif(not DB.exists(), reason="processed database unavailable")
def test_agent_investigation_uses_cross_tool_and_conservative_language() -> None:
    top = detect_cross_domain_anomalies("2026-07", "2026-06", DB)[0]
    graph = MobilityAgentGraph(UnavailableProvider())
    state = graph.graph.invoke({
        "request_id": "test", "endpoint": "agent.investigate", "mode": "investigate",
        "question": f"Investigate anomaly {top.id}", "month": "2026-07",
        "baseline_month": "2026-06", "anomaly_id": top.id, "started_at": 0.0,
    })
    response = state["response"]
    assert "detect_cross_domain_anomalies_tool" in state["tools_called"]
    assert response.findings
    blob = json.dumps(response.model_dump()).lower()
    assert not any(phrase in blob for phrase in BANNED)
