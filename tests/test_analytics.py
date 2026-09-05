from pathlib import Path

import pytest

from app.analytics.anomaly_detection import classify_change, detect_anomalies
from app.analytics.service import AnalyticsService, compare_values, safe_rate
from app.models.analytics import MonthlyOverview

DB = Path("data/processed/mobility.duckdb")


def test_rate_and_division_by_zero() -> None:
    assert safe_rate(5, 10) == 0.5
    assert safe_rate(5, 0) is None


def test_baseline_comparison() -> None:
    assert compare_values(0.12, 0.10) == (0.02, 20.0)
    assert compare_values(1, 0) == (1.0, None)


def test_small_sample_protection_and_severity() -> None:
    assert classify_change("delay_rate", 0.2, 0.1, 100)[0] is None
    assert classify_change("delay_rate", 0.15, 0.1, 1000)[0] == "high"
    assert classify_change("no_show_rate", 0.05, 0.08, 1000)[0] == "positive"


@pytest.mark.skipif(not DB.exists(), reason="processed database unavailable")
def test_actual_overview_schema_and_missing_month() -> None:
    service = AnalyticsService(DB)
    result = service.get_monthly_overview("2026-07")
    assert isinstance(result, MonthlyOverview)
    assert result.metrics["total_trips"].current_value == 215885
    with pytest.raises(ValueError):
        service.get_monthly_overview("2099-01")


@pytest.mark.skipif(not DB.exists(), reason="processed database unavailable")
def test_cost_exclusion_and_rating_zero_handling() -> None:
    service = AnalyticsService(DB)
    cost = service.analyze_cost("2026-07")
    assert cost.excluded_distance_rows > 0
    assert cost.valid_distance_rows + cost.excluded_distance_rows == cost.billed_rows
    experience = service.get_experience_metrics("2026-07")
    assert experience.dimensions["marshal"]["nonzero_average"] >= experience.dimensions["marshal"]["raw_average"]


@pytest.mark.skipif(not DB.exists(), reason="processed database unavailable")
def test_missing_vendor_and_anomaly_schema() -> None:
    service = AnalyticsService(DB)
    with pytest.raises(ValueError):
        service.analyze_vendor("missing-vendor", "2026-07", "2026-05")
    anomalies = detect_anomalies("2026-07", DB)
    assert anomalies
    assert anomalies[0].model_dump()["id"].startswith("anomaly-")

