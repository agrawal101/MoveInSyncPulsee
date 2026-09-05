from fastapi import APIRouter,Query
from app.analytics.service import get_monthly_overview
from app.models.analytics import MonthlyOverview
router=APIRouter(tags=["overview"])
@router.get("/overview",response_model=MonthlyOverview)
def overview(month:str=Query(pattern=r"^\d{4}-\d{2}$"))->MonthlyOverview:return get_monthly_overview(month)

