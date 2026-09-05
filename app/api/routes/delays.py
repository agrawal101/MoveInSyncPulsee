from fastapi import APIRouter,Query
from app.analytics.service import analyze_delay_causes
from app.models.agent import DelayAnalysisResponse
router=APIRouter(tags=["operations"])
@router.get("/delays/causes",response_model=DelayAnalysisResponse)
def delays(month:str=Query(pattern=r"^\d{4}-\d{2}$"),vendor:str|None=None,office:str|None=None,shift:str|None=None)->DelayAnalysisResponse:return DelayAnalysisResponse.model_validate(analyze_delay_causes(month,vendor,office,shift))

