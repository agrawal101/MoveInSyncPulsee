from fastapi import APIRouter,Query
from app.analytics.service import analyze_safety_alerts
from app.models.analytics import SafetyAnalysis
router=APIRouter(tags=["safety"])
@router.get("/safety",response_model=SafetyAnalysis)
def safety(month:str=Query(pattern=r"^\d{4}-\d{2}$"),vendor:str|None=None,office:str|None=None)->SafetyAnalysis:return analyze_safety_alerts(month,vendor,office)

