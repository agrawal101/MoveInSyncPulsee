from fastapi import APIRouter,Query
from app.analytics.service import analyze_cost
from app.models.analytics import CostAnalysis
router=APIRouter(tags=["cost"])
@router.get("/cost",response_model=CostAnalysis)
def cost(month:str=Query(pattern=r"^\d{4}-\d{2}$"),vendor:str|None=None)->CostAnalysis:return analyze_cost(month,vendor)

