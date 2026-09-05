from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from app.analytics.anomaly_detection import detect_anomalies
from app.analytics.service import AnalyticsService

service = AnalyticsService()
payload = {"overview": service.get_monthly_overview("2026-07").model_dump(), "vendor_comparison": service.compare_vendor_performance("2026-07", "2026-05").model_dump(), "shift_readiness": service.get_shift_readiness("2026-07").model_dump(), "safety": service.analyze_safety_alerts("2026-07").model_dump(), "cost": service.analyze_cost("2026-07").model_dump(), "experience": service.get_experience_metrics("2026-07").model_dump(), "anomalies": [a.model_dump() for a in detect_anomalies("2026-07")]}
print(json.dumps(payload, indent=2, default=str))

