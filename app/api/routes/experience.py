from fastapi import APIRouter,Query
from app.analytics.service import get_experience_metrics
from app.models.analytics import ExperienceAnalysis
router=APIRouter(tags=["experience"])
@router.get("/experience",response_model=ExperienceAnalysis)
def experience(month:str=Query(pattern=r"^\d{4}-\d{2}$"),vendor:str|None=None)->ExperienceAnalysis:return get_experience_metrics(month,vendor)

