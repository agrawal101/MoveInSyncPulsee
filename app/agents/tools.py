from __future__ import annotations
from langchain_core.tools import tool
from app.analytics.anomaly_detection import detect_anomalies
from app.analytics.cross_domain_anomalies import detect_cross_domain_anomalies
from app.analytics.service import AnalyticsService

def _dump(value):
    if isinstance(value, list): return [item.model_dump() if hasattr(item, "model_dump") else item for item in value]
    return value.model_dump() if hasattr(value, "model_dump") else value

@tool
def get_monthly_overview_tool(month: str) -> dict:
    """Return deterministic monthly KPIs and comparisons. Requires YYYY-MM; ratings retain quality warnings."""
    return _dump(AnalyticsService().get_monthly_overview(month))

@tool
def compare_vendor_performance_tool(current_month: str, baseline_month: str) -> dict:
    """Compare normalized vendor delay, alert, no-show, cost, and rating metrics. Requires two available months."""
    return _dump(AnalyticsService().compare_vendor_performance(current_month, baseline_month))

@tool
def analyze_vendor_tool(vendor: str, month: str, baseline_month: str | None = None) -> dict:
    """Analyze one exact vendor and peer rank. Requires vendor/month; missing joins and sparse samples limit confidence."""
    return _dump(AnalyticsService().analyze_vendor(vendor, month, baseline_month))

@tool
def get_shift_readiness_tool(month: str) -> dict:
    """Rank shifts using actual-vs-planned pickup lateness and no-shows. Requires month; small samples remain visible."""
    return _dump(AnalyticsService().get_shift_readiness(month))

@tool
def analyze_safety_alerts_tool(month: str, vendor: str | None = None, office: str | None = None) -> dict:
    """Return normalized alerts, types, severity, concentration, response time, and repeated vehicles. No driver identity exists."""
    return _dump(AnalyticsService().analyze_safety_alerts(month, vendor, office))

@tool
def analyze_delay_causes_tool(month: str, vendor: str | None = None, office: str | None = None, shift: str | None = None) -> dict:
    """Rank delay reasons and return trip evidence, with optional vendor/office/shift drill-down."""
    return AnalyticsService().analyze_delay_causes(month, vendor, office, shift)

@tool
def analyze_cost_tool(month: str, vendor: str | None = None) -> dict:
    """Return billing and defensible cost/km metrics. Invalid cost/distance rows are excluded with coverage disclosed."""
    return _dump(AnalyticsService().analyze_cost(month, vendor))

@tool
def get_experience_metrics_tool(month: str, vendor: str | None = None) -> dict:
    """Return raw and non-zero feedback metrics. Zero may mean not-rated and must not be called dissatisfaction."""
    return _dump(AnalyticsService().get_experience_metrics(month, vendor))

@tool
def get_data_quality_report_tool() -> dict:
    """Return joins, invalid values, nulls, rating semantics, and preprocessing quality evidence."""
    return AnalyticsService().get_data_quality_report()

@tool
def detect_anomalies_tool(month: str) -> list[dict]:
    """Return deterministic negative and positive anomalies using prior-month and peer comparisons with minimum samples."""
    return _dump(detect_anomalies(month))

@tool
def detect_cross_domain_anomalies_tool(month: str, baseline_month: str | None = None) -> list[dict]:
    """Return deterministic CROSS-DOMAIN anomalies: suspicious combinations that correlate billing, safety, service, shift, and data-quality signals (potential billing irregularities, safety divergence, vendor divergence, shift readiness, data integrity). Prefer for questions about suspicious patterns, possible billing irregularity/reconciliation, unusual cross-signal vendor behavior, or anomalies a normal report would miss. The engine detects deterministically; never assert fraud."""
    return _dump(detect_cross_domain_anomalies(month, baseline_month))

TOOLS = [get_monthly_overview_tool, compare_vendor_performance_tool, analyze_vendor_tool, get_shift_readiness_tool, analyze_safety_alerts_tool, analyze_delay_causes_tool, analyze_cost_tool, get_experience_metrics_tool, get_data_quality_report_tool, detect_anomalies_tool, detect_cross_domain_anomalies_tool]
TOOL_REGISTRY = {item.name: item for item in TOOLS}

